from datetime import date, timedelta

from django.db import transaction

from apps.index.models import Episode, Subject
from apps.sync.providers.bangumi import BangumiAPIError, bangumi_client
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.subject_service import subject_service


class EpisodeService:
    INFO_SOURCE = "bangumi_episode"

    def sync_subject_episodes(self, bangumi_id: int) -> None:
        subject = subject_service.provide_subject(bangumi_id)
        limit = 100
        offset = 0
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
            if len(data) == 0:
                break
            self._upsert_episodes(subject, data)
            if len(data) < limit:
                break
            offset += limit

    def _upsert_episodes(self, subject: Subject, data: list[dict]) -> None:
        if not data:
            return

        id_map = {}
        for item in data:
            bangumi_id = item.get("id")
            if not bangumi_id:
                continue
            id_map[str(bangumi_id)] = item
        if not id_map:
            return

        episodes = []
        for id_source, item in id_map.items():
            mapped = self._map_episode_data(item)
            episodes.append(
                Episode(
                    info_source=self.INFO_SOURCE,
                    id_source=id_source,
                    subject=subject,
                    **mapped,
                )
            )

        with transaction.atomic():
            Episode.objects.bulk_create(
                episodes,
                batch_size=100,
                update_conflicts=True,
                update_fields=[
                    "title",
                    "type",
                    "ep_num",
                    "sort",
                    "duration",
                    "date",
                    "description",
                    "subject",
                ],
                unique_fields=["info_source", "id_source"],
            )

    def _map_episode_data(self, data: dict) -> dict:
        return {
            "title": self._parse_episode_title(data),
            "type": self._parse_episode_type(data),
            "ep_num": self._parse_episode_ep_num(data),
            "sort": self._parse_episode_sort(data),
            "duration": self._parse_episode_duration(data),
            "date": self._parse_episode_air_date(data),
            "description": self._parse_episode_description(data),
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

    def _parse_episode_ep_num(self, data: dict) -> int | None:
        ep_num = data.get("ep")
        return ep_num if isinstance(ep_num, int) else None

    def _parse_episode_sort(self, data: dict) -> int | None:
        sort = data.get("sort")
        return sort if isinstance(sort, int) else None

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
