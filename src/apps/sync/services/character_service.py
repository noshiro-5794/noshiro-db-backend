from apps.index.models import Character
from apps.sync.providers.bangumi import BangumiAPIError, bangumi_client
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.name_normalizer import name_normalizer


class CharacterService:
    INFO_SOURCE = "bangumi_character"

    def upsert_character(self, bangumi_id: int) -> Character:
        data = bangumi_client.fetch_character(bangumi_id)
        if not isinstance(data, dict) or not data:
            raise BangumiAPIError("Bangumi character response must be an object.")
        mapped_data = self._map_character_data(data)
        character, _ = Character.objects.update_or_create(
            info_source=self.INFO_SOURCE,
            id_source=str(bangumi_id),
            defaults=mapped_data,
        )
        return character

    def provide_character(self, bangumi_id: int | str) -> Character:
        character, _ = Character.objects.get_or_create(
            info_source=self.INFO_SOURCE,
            id_source=str(bangumi_id),
        )
        return character

    def _map_character_data(self, data: dict) -> dict:
        return {
            "name": self._parse_character_name(data),
            "description": self._parse_character_description(data),
            "gender": self._parse_character_gender(data),
            "birth": self._parse_character_birth(data),
            "type": self._parse_character_type(data),
            "blood_type": self._parse_character_blood_type(data),
            "image_original": self._parse_character_image_original(data),
            "image_thumbnail": self._parse_character_image_thumbnail(data),
            "infobox": self._parse_character_infobox(data),
        }

    def _parse_character_name(self, data: dict) -> str:
        return clean_string(data.get("name"), max_length=256)

    def _parse_character_description(self, data: dict) -> str:
        return clean_string(data.get("summary"))

    def _parse_character_gender(self, data: dict) -> str:
        return clean_string(data.get("gender"), max_length=64)

    def _parse_character_birth(self, data: dict) -> dict:
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

    def _parse_character_type(self, data: dict) -> str:
        character_type_mapping = {
            1: "Character",
            2: "Mech",
            3: "Ship",
            4: "Organization",
        }
        t = data.get("type")
        if not isinstance(t, int):
            return ""
        return character_type_mapping.get(t) if t in character_type_mapping else ""

    def _parse_character_blood_type(self, data: dict) -> str:
        character_blood_type_mapping = {
            1: "A",
            2: "B",
            3: "AB",
            4: "O",
        }
        blood_type = data.get("blood_type")
        if not isinstance(blood_type, int):
            return ""
        return (
            character_blood_type_mapping.get(blood_type)
            if blood_type in character_blood_type_mapping
            else ""
        )

    def _parse_character_image_original(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("large"), max_length=1024)

    def _parse_character_image_thumbnail(self, data: dict) -> str:
        images = data.get("images")
        if not isinstance(images, dict):
            return ""
        return clean_string(images.get("medium"), max_length=1024)

    def _parse_character_infobox(self, data: dict) -> list:
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


character_service = CharacterService()
