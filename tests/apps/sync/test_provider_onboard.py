from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.index.models import Provider

pytestmark = pytest.mark.django_db(transaction=True)


def _run(*args) -> str:
    out = StringIO()
    call_command("provider_onboard", *args, stdout=out)
    return out.getvalue()


def test_dry_run_does_not_persist() -> None:
    output = _run(
        "vndb",
        "--policy",
        "storage=allowed",
        "--policy",
        "ai_usage=restricted",
        "--enable",
    )

    assert "[dry-run]" in output
    assert "would be created" in output
    assert not Provider.objects.filter(slug="vndb").exists()


def test_apply_creates_provider_with_explicit_policies() -> None:
    output = _run(
        "vndb",
        "--policy",
        "storage=allowed",
        "--policy",
        "redistribution=restricted",
        "--policy",
        "commercial_use=restricted",
        "--policy",
        "ai_usage=restricted",
        "--terms-checked",
        "--enable",
        "--apply",
    )

    provider = Provider.objects.get(slug="vndb")
    assert provider.is_enabled is True
    assert provider.storage_policy == Provider.UsagePolicy.ALLOWED
    assert provider.redistribution_policy == Provider.UsagePolicy.RESTRICTED
    assert provider.ai_usage_policy == Provider.UsagePolicy.RESTRICTED
    assert provider.terms_checked_at is not None
    assert provider.license_name == "ODbL"
    assert "created" in output


def test_apply_is_idempotent_on_existing_provider() -> None:
    first = _run(
        "anilist",
        "--policy",
        "storage=allowed",
        "--enable",
        "--apply",
    )
    second = _run(
        "anilist",
        "--policy",
        "storage=allowed",
        "--enable",
        "--apply",
    )

    assert "no changes" in second
    assert Provider.objects.filter(slug="anilist").count() == 1
    assert "created" in first


def test_invalid_policy_value_is_rejected() -> None:
    with pytest.raises(CommandError, match="Invalid value"):
        _run("bangumi", "--policy", "storage=everything", "--apply")


def test_enable_and_disable_are_mutually_exclusive() -> None:
    with pytest.raises(CommandError, match="mutually exclusive"):
        _run("bangumi", "--enable", "--disable", "--apply")
