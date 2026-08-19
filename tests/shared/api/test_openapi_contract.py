import json
from pathlib import Path

from drf_spectacular.generators import SchemaGenerator

SNAPSHOT_PATH = Path(__file__).parents[2] / "snapshots" / "openapi.json"


def current_schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_openapi_schema_matches_the_committed_contract() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert current_schema() == expected


def test_openapi_exposes_only_the_single_v1_api() -> None:
    paths = current_schema()["paths"]

    assert paths
    assert all(path.startswith("/api/v1/") for path in paths)
    assert not any(path.startswith("/api/v2/") for path in paths)
