from apps.index.models import Staff
from apps.sync.providers.bangumi import BangumiAPIError, bangumi_client
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.name_normalizer import name_normalizer


class StaffService:
    INFO_SOURCE = "bangumi_persons"

    def upsert_staff(self, bangumi_id: int) -> Staff:
        data = bangumi_client.fetch_person(bangumi_id)
        if not isinstance(data, dict) or not data:
            raise BangumiAPIError("Bangumi person response must be an object.")
        mapped_data = self._map_staff_data(data)
        staff, _ = Staff.objects.update_or_create(
            info_source=self.INFO_SOURCE,
            id_source=str(bangumi_id),
            defaults=mapped_data,
        )
        return staff

    def provide_staff(self, bangumi_id: int | str) -> Staff:
        staff, _ = Staff.objects.get_or_create(
            info_source=self.INFO_SOURCE,
            id_source=str(bangumi_id),
        )
        return staff

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
        month = data.get("birth_month")
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
