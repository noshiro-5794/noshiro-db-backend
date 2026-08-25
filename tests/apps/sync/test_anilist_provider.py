from apps.sync.services.anilist_service import AniListImportService


def test_anilist_integer_and_date_helpers() -> None:
    assert AniListImportService._as_int("12") == 12
    assert AniListImportService._as_int(True) is None
    assert AniListImportService._as_int("abc") is None
    assert AniListImportService._as_date({"year": 2026, "month": 8}) == "2026-08-01"
    assert AniListImportService._as_date({"year": 2026}) is None


def test_anilist_work_type_mapping() -> None:
    assert AniListImportService._work_type_from_format("TV") == "anime"
    assert AniListImportService._work_type_from_format("NOVEL") == "other"
