from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.index.models import Episode, EpisodeExternalIdentity, Subject
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.bangumi import (
    BANGUMI_EPISODE_NAMESPACE,
    BANGUMI_SUBJECT_EPISODES_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.source_record_service import (
    source_identity_service,
    source_record_service,
)
from apps.sync.services.subject_service import subject_service


class EpisodeService:
    INFO_SOURCE = "bangumi_episode"

    def sync_subject_episodes(self, bangumi_id: int) -> None:
        limit = 100
        offset = 0
        items = []
        while True:
            resp = bangumi_client.fetch_subject_episodes(
                subject_id=bangumi_id,
                limit=limit,
                offset=offset,
            )
            if not isinstance(resp, dict):
                raise BangumiAPIError("Bangumi episode response must be an object.")
            data = resp.get("data")
            if not isinstance(data, list):
                raise BangumiAPIError("Bangumi episode response is missing data.")
            items.extend(data)
            if len(data) < limit:
                break
            offset += limit
        subject = subject_service.provide_subject(bangumi_id)
        self._upsert_episodes(subject, items)

    def _upsert_episodes(self, subject: Subject, data: list[dict]) -> None:
        with transaction.atomic():
            return self._persist_episodes(subject, data)

    def _persist_episodes(self, subject: Subject, data: list[dict]) -> None:
        id_map = {}
        index_by_id = {}
        for index, item in enumerate(data):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            external_id = str(item["id"])
            id_map[external_id] = item
            index_by_id[external_id] = index
        collection_recorded = source_record_service.record(
            namespace_spec=BANGUMI_SUBJECT_EPISODES_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=subject.id_source,
                payload={"items": data},
                canonical_url=f"https://bgm.tv/subject/{subject.id_source}/ep",
                schema_version="bangumi-api-v0",
                mapper_version="bangumi-subject-episodes-v1",
            ),
        )
        relationship_observation = knowledge_ingestion_service.record_observation(
            provider_record=collection_recorded.record,
            mapper="bangumi.subject-episodes",
            mapper_version="bangumi-subject-episodes-v1",
            normalized_data={"items": data},
            schema_name="index.work.episodes",
            schema_version="1",
        )
        if not id_map:
            return

        recorded_by_id = source_record_service.record_many(
            namespace_spec=BANGUMI_EPISODE_NAMESPACE,
            fetched_records=[
                FetchedSourceRecord(
                    external_id=id_source,
                    payload=item,
                    canonical_url=f"https://bgm.tv/ep/{id_source}",
                    schema_version="bangumi-api-v0",
                    mapper_version="bangumi-episode-v1",
                )
                for id_source, item in id_map.items()
            ],
        )

        persisted_episodes = source_identity_service.resolve_episodes(
            namespace_spec=BANGUMI_EPISODE_NAMESPACE,
            external_ids=set(id_map),
            legacy_source=self.INFO_SOURCE,
        )
        episodes_to_upsert = []
        episodes_to_update = []
        now = timezone.now()
        for id_source, item in id_map.items():
            mapped = self._map_episode_data(item)
            episode = persisted_episodes.get(id_source)
            if episode is None:
                episodes_to_upsert.append(
                    Episode(
                        info_source=self.INFO_SOURCE,
                        id_source=id_source,
                        subject=subject,
                        **mapped,
                    )
                )
                continue

            for field, value in mapped.items():
                setattr(episode, field, value)
            episode.subject = subject
            episode.updated_at = now
            episodes_to_update.append(episode)

        update_fields = [
            "title",
            "title_cn",
            "type",
            "ep_num",
            "sort",
            "duration",
            "date",
            "description",
            "disc",
            "comment_count",
            "raw_duration",
            "subject",
            "updated_at",
        ]
        if episodes_to_upsert:
            Episode.objects.bulk_create(
                episodes_to_upsert,
                batch_size=100,
                update_conflicts=True,
                update_fields=update_fields,
                unique_fields=["info_source", "id_source"],
            )
        if episodes_to_update:
            Episode.objects.bulk_update(
                episodes_to_update,
                fields=update_fields,
                batch_size=100,
            )

        missing_ids = set(id_map) - set(persisted_episodes)
        persisted_episodes.update(
            {
                episode.id_source: episode
                for episode in Episode.objects.filter(
                    info_source=self.INFO_SOURCE,
                    id_source__in=missing_ids,
                )
            }
        )
        if set(persisted_episodes) != set(id_map):
            missing = sorted(set(id_map) - set(persisted_episodes))
            raise RuntimeError(
                f"Bangumi episodes were not persisted: {', '.join(missing)}"
            )
        source_identity_service.bind_episodes(
            bindings=[
                (persisted_episodes[id_source], recorded_by_id[id_source].record)
                for id_source in id_map
            ],
            match_method=EpisodeExternalIdentity.MatchMethod.PROVIDER,
        )
        for id_source, item in id_map.items():
            knowledge_ingestion_service.project_episode(
                episode=persisted_episodes[id_source],
                provider_record=recorded_by_id[id_source].record,
                normalized_data=item,
                relationship_observation=relationship_observation,
                relationship_json_pointer=f"/items/{index_by_id[id_source]}",
                mapper_version="bangumi-episode-v1",
            )

    def _map_episode_data(self, data: dict) -> dict:
        return {
            "title": self._parse_episode_title(data),
            "title_cn": clean_string(data.get("name_cn"), max_length=256),
            "type": self._parse_episode_type(data),
            "ep_num": self._parse_episode_ep_num(data),
            "sort": self._parse_episode_sort(data),
            "duration": self._parse_episode_duration(data),
            "date": self._parse_episode_air_date(data),
            "description": self._parse_episode_description(data),
            "disc": self._parse_non_negative_int(data.get("disc")),
            "comment_count": self._parse_non_negative_int(data.get("comment")),
            "raw_duration": clean_string(data.get("duration"), max_length=64),
        }

    def _parse_episode_title(self, data: dict) -> str:
        return clean_string(data.get("name"), max_length=256)

    def _parse_episode_type(self, data: dict) -> str:
        episode_type_mapping = {
            0: "EP",
            1: "SP",
            2: "OP",
            3: "ED",
            4: "PV/CM",
            5: "MAD",
            6: "ETC",
        }
        t = data.get("type")
        if not isinstance(t, int):
            return ""
        return episode_type_mapping.get(t) if t in episode_type_mapping else ""

    def _parse_episode_ep_num(self, data: dict) -> Decimal | None:
        return self._parse_decimal(data.get("ep"))

    def _parse_episode_sort(self, data: dict) -> Decimal | None:
        return self._parse_decimal(data.get("sort"))

    @staticmethod
    def _parse_decimal(value) -> Decimal | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _parse_non_negative_int(value) -> int | None:
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else None
        )

    def _parse_episode_duration(self, data: dict) -> timedelta | None:
        duration = data.get("duration_seconds")
        if not isinstance(duration, int):
            return None
        if duration <= 0:
            return None
        return timedelta(seconds=duration)

    def _parse_episode_air_date(self, data: dict) -> date | None:
        value = clean_string(data.get("airdate"))
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _parse_episode_description(self, data: dict) -> str:
        return clean_string(data.get("desc"))


episode_service = EpisodeService()
