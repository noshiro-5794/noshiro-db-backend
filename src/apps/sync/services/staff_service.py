from django.db import transaction

from apps.index.models import Contributor, ProviderRepresentation, SourceRecord
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.bangumi import (
    BANGUMI_PERSON_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.name_normalizer import name_normalizer
from apps.sync.services.source_record_service import source_record_service


class StaffService:
    INFO_SOURCE = "bangumi_persons"

    def upsert_staff(self, bangumi_id: int) -> Contributor:
        data = bangumi_client.fetch_person(bangumi_id)
        if not isinstance(data, dict) or not data:
            raise BangumiAPIError("Bangumi person response must be an object.")
        recorded = source_record_service.record(
            namespace_spec=BANGUMI_PERSON_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=str(bangumi_id),
                payload=data,
                canonical_url=f"https://bgm.tv/person/{bangumi_id}",
                schema_version="bangumi-api-v0",
                mapper_version="bangumi-person-v1",
            ),
        )
        mapped_data = self._map_staff_data(data)
        with transaction.atomic():
            return knowledge_ingestion_service.project_contributor_from_record(
                provider_record=recorded.record,
                normalized_data=data,
                mapped_data=mapped_data,
                mapper="bangumi.person",
                mapper_version="bangumi-person-v1",
            )

    def provide_staff(self, bangumi_id: int | str) -> Contributor:
        external_id = str(bangumi_id)
        record = source_record_service.ensure_record(
            namespace_spec=BANGUMI_PERSON_NAMESPACE,
            external_id=external_id,
            origin=SourceRecord.Origin.API,
            canonical_url=f"https://bgm.tv/person/{external_id}",
        )
        with transaction.atomic():
            entity = self._resolve_entity(record)
            if (
                entity is not None
                and Contributor.objects.filter(entity=entity).exists()
            ):
                return Contributor.objects.get(entity=entity)
            payload = (
                record.latest_revision.payload
                if record.latest_revision_id
                else {"embedded": True, "id": external_id}
            )
            return knowledge_ingestion_service.project_contributor_from_record(
                provider_record=record,
                normalized_data=payload,
                mapped_data=self._map_staff_data(payload),
                mapper="bangumi.person",
                mapper_version="bangumi-person-placeholder-v1",
            )

    @staticmethod
    def _resolve_entity(record: SourceRecord):
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=record,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        return representation.entity if representation is not None else None

    def _map_staff_data(self, data: dict) -> dict:
        return {
            "name": self._parse_staff_name(data),
            "description": self._parse_staff_description(data),
            "gender": self._parse_staff_gender(data),
            "birth": self._parse_staff_birth(data),
            "type": self._parse_staff_type(data),
            "career": self._parse_staff_career(data),
            "image_original": self._parse_staff_image_original(data),
            "image_thumbnail": self._parse_staff_image_thumbnail(data),
            "infobox": self._parse_staff_infobox(data),
        }

    def _parse_staff_name(self, data: dict) -> str:
        return clean_string(data.get("name"), max_length=256)

    def _parse_staff_description(self, data: dict) -> str:
        return clean_string(data.get("summary"))

    def _parse_staff_gender(self, data: dict) -> str:
        return clean_string(data.get("gender"), max_length=64)

    def _parse_staff_birth(self, data: dict) -> dict:
        birth = {}
        year = data.get("birth_year")
        month = data.get("birth_mon", data.get("birth_month"))
        day = data.get("birth_day")
        if isinstance(year, int):
            birth["year"] = year
        if isinstance(month, int):
            birth["month"] = month
        if isinstance(day, int):
            birth["day"] = day
        return birth

    def _parse_staff_type(self, data: dict) -> str:
        staff_type_mapping = {
            1: "Individual",
            2: "Company",
            3: "Group",
        }
        t = data.get("type")
        if not isinstance(t, int):
            return ""
        return staff_type_mapping.get(t) if t in staff_type_mapping else ""

    def _parse_staff_career(self, data: dict) -> list:
        career = data.get("career")
        if not isinstance(career, list):
            return []
        result = []
        for item in career:
            if isinstance(item, str):
                normalized = name_normalizer.normalize_name(item.strip())
                if normalized:
                    result.append(normalized)
        return result

    def _parse_staff_image_original(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("large"), max_length=1024)

    def _parse_staff_image_thumbnail(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("medium"), max_length=1024)

    def _parse_staff_infobox(self, data: dict) -> list:
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


staff_service = StaffService()
