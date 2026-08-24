from datetime import date

from django.db import transaction

from apps.index.models import (
    Entity,
    ProviderRepresentation,
    SourceRecord,
    Work,
)
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.bangumi import (
    BANGUMI_SUBJECT_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.name_normalizer import name_normalizer
from apps.sync.services.source_record_service import source_record_service


class SubjectService:
    INFO_SOURCE = "bangumi_subject"
    GALGAME_META_TAG = "galgame"

    def upsert_subject(self, bangumi_id: int) -> Entity:
        data = bangumi_client.fetch_subject(bangumi_id)
        if not isinstance(data, dict) or not data:
            raise BangumiAPIError("Bangumi subject response must be an object.")
        recorded = source_record_service.record(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=str(bangumi_id),
                payload=data,
                canonical_url=f"https://bgm.tv/subject/{bangumi_id}",
                schema_version="bangumi-api-v0",
                mapper_version="bangumi-subject-v1",
            ),
        )
        mapped_data = self._map_subject_data(data)
        with transaction.atomic():
            return knowledge_ingestion_service.project_work_from_record(
                provider_record=recorded.record,
                normalized_data=data,
                mapped_data=mapped_data,
                mapper_version="bangumi-subject-v1",
            )

    def provide_subject(self, bangumi_id: int | str) -> Entity:
        external_id = str(bangumi_id)
        record = source_record_service.ensure_record(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            external_id=external_id,
            origin=SourceRecord.Origin.API,
            canonical_url=f"https://bgm.tv/subject/{external_id}",
        )
        with transaction.atomic():
            entity = self._resolve_entity(record)
            if entity is not None and Work.objects.filter(pk=entity.pk).exists():
                return entity
            payload = (
                record.latest_revision.payload
                if record.latest_revision_id
                else {"embedded": True, "id": external_id}
            )
            return knowledge_ingestion_service.project_work_from_record(
                provider_record=record,
                normalized_data=payload,
                mapped_data=self._map_subject_data(payload),
                mapper_version="bangumi-subject-placeholder-v1",
            )

    @staticmethod
    def _resolve_entity(record: SourceRecord) -> Entity | None:
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=record,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        return representation.entity if representation is not None else None

    def _map_subject_data(self, data: dict) -> dict:
        return {
            "subject_type": self._parse_subject_type(data),
            "title": self._parse_subject_title(data),
            "title_cn": self._parse_subject_title_cn(data),
            "date": self._parse_subject_date(data),
            "image_original": self._parse_subject_image_original(data),
            "image_thumbnail": self._parse_subject_image_thumbnail(data),
            "platform": self._parse_subject_platform(data),
            "description": self._parse_subject_description(data),
            "nsfw": self._parse_subject_nsfw(data),
            "series": self._parse_subject_series(data),
            "volumes": self._parse_subject_volumes(data),
            "eps": self._parse_subject_eps(data),
            "total_episodes": self._parse_subject_total_episodes(data),
            "infobox": self._parse_subject_infobox(data),
            "tags": self._parse_subject_tags(data),
        }

    def _parse_subject_type(self, data: dict) -> str:
        type_id = data.get("type")
        if not isinstance(type_id, int):
            return "other"
        type_mapping = {
            1: lambda: self._parse_subject_type_book(data),
            2: lambda: "anime",
            3: lambda: "music",
            4: lambda: self._parse_subject_type_game(data),
            6: lambda: "other",
        }
        return type_mapping.get(type_id, lambda: "other")()

    def _parse_subject_type_book(self, data: dict) -> str:
        platform = data.get("platform")
        if isinstance(platform, str):
            if "小说" in platform:
                return "novel"
            elif "漫画" in platform:
                return "manga"
        return "book"

    def _parse_subject_type_game(self, data: dict) -> str:
        for tag in self._parse_subject_meta_tags(data):
            if tag.lower() == self.GALGAME_META_TAG:
                return "galgame"
        return "game"

    def _parse_subject_title(self, data: dict) -> str:
        return clean_string(data.get("name"), max_length=256)

    def _parse_subject_title_cn(self, data: dict) -> str:
        return clean_string(data.get("name_cn"), max_length=256)

    def _parse_subject_date(self, data: dict) -> date | None:
        value = clean_string(data.get("date"))
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _parse_subject_image_original(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("large"), max_length=1024)

    def _parse_subject_image_thumbnail(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("medium"), max_length=1024)

    def _parse_subject_platform(self, data: dict) -> str:
        platform = clean_string(data.get("platform"))
        return name_normalizer.normalize_name(platform)[:256] if platform else ""

    def _parse_subject_description(self, data: dict) -> str:
        return clean_string(data.get("summary"))

    def _parse_subject_nsfw(self, data: dict) -> bool:
        nsfw = data.get("nsfw")
        return nsfw if isinstance(nsfw, bool) else False

    def _parse_subject_series(self, data: dict) -> bool:
        series = data.get("series")
        return series if isinstance(series, bool) else False

    def _parse_subject_volumes(self, data: dict) -> int | None:
        volumes = data.get("volumes")
        return volumes if isinstance(volumes, int) else None

    def _parse_subject_eps(self, data: dict) -> int | None:
        eps = data.get("eps")
        return eps if isinstance(eps, int) else None

    def _parse_subject_total_episodes(self, data: dict) -> int | None:
        total_episodes = data.get("total_episodes")
        return total_episodes if isinstance(total_episodes, int) else None

    def _parse_subject_infobox(self, data: dict) -> list:
        infobox = data.get("infobox")
        if not isinstance(infobox, list):
            return []
        result = []
        for item in infobox:
            parsed = self._parse_infobox_item(item)
            if parsed:
                result.append(parsed)
        return result

    def _parse_infobox_item(self, item: dict) -> dict | None:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        normalized_key = ""
        if isinstance(key, str):
            normalized_key = name_normalizer.normalize_name(key.strip())
        value = item.get("value")
        normalized_value = self._normalize_infobox_value(value)
        if not normalized_key and not normalized_value:
            return None
        return {"key": normalized_key, "value": normalized_value}

    def _normalize_infobox_value(self, value) -> list:
        result: list[str] = []
        if isinstance(value, str):
            result.append(value.strip())
            return result
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    v = item.get("v")
                    if isinstance(v, str):
                        result.append(v.strip())
            return result
        return []

    def _parse_subject_tags(self, data: dict) -> list:
        result = []
        for tag in self._parse_subject_meta_tags(data):
            normalized = name_normalizer.normalize_name(tag)
            if normalized:
                result.append(normalized)
        return result

    def _parse_subject_meta_tags(self, data: dict) -> list[str]:
        tags = data.get("meta_tags")
        if tags is None:
            tags = data.get("metatag")
        if not isinstance(tags, list):
            return []

        return [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]


subject_service = SubjectService()
