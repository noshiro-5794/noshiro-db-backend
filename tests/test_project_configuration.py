from django.apps import apps
from django.conf import settings
from django.core.checks import run_checks

from config.settings.environment import env_list


def test_expected_project_apps_are_installed() -> None:
    installed_apps = {app_config.name for app_config in apps.get_app_configs()}

    assert {
        "apps.community",
        "apps.index",
        "apps.sync",
        "apps.users",
    } <= installed_apps


def test_django_system_checks_pass() -> None:
    assert run_checks() == []


def test_comma_separated_environment_values_are_cleaned(monkeypatch) -> None:
    monkeypatch.setenv("NOSHIRO_TEST_LIST", "alpha, beta,,gamma ")

    assert env_list("NOSHIRO_TEST_LIST") == ["alpha", "beta", "gamma"]


def test_test_database_is_isolated() -> None:
    database = settings.DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["NAME"].endswith("_test")
    assert database["TEST"]["NAME"] == database["NAME"]
    assert database["CONN_MAX_AGE"] == 0
    assert database["CONN_HEALTH_CHECKS"] is False
    assert "sslmode" not in database.get("OPTIONS", {})


def test_representative_database_table_names_are_stable() -> None:
    expected_tables = {
        "community.CommunityPost": "community_post",
        "index.Subject": "subject",
        "sync.SyncJob": "sync_job",
        "users.Collection": "collection",
        "users.User": "user",
    }

    actual_tables = {
        model_label: apps.get_model(model_label)._meta.db_table
        for model_label in expected_tables
    }

    assert actual_tables == expected_tables
