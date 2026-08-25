import re
from collections.abc import Callable
from dataclasses import dataclass

from apps.sync.models import SyncJob
from apps.sync.tasks.anilist import import_anilist_media_task
from apps.sync.tasks.vndb import import_vndb_work_task


@dataclass(frozen=True, slots=True)
class ImportProvider:
    slug: str
    label: str
    job_type: str
    external_id_pattern: re.Pattern[str]
    dispatch: Callable
    default_include_related: bool = True


IMPORT_PROVIDERS: dict[str, ImportProvider] = {
    "vndb": ImportProvider(
        slug="vndb",
        label="VNDB",
        job_type=SyncJob.JobType.VNDB_IMPORT,
        external_id_pattern=re.compile(r"^v[1-9][0-9]*$"),
        dispatch=import_vndb_work_task.delay,
    ),
    "anilist": ImportProvider(
        slug="anilist",
        label="AniList",
        job_type=SyncJob.JobType.ANILIST_IMPORT,
        external_id_pattern=re.compile(r"^[1-9][0-9]*$"),
        dispatch=import_anilist_media_task.delay,
        default_include_related=True,
    ),
}


def import_provider_choices() -> tuple[tuple[str, str], ...]:
    return tuple(
        (provider.slug, provider.label) for provider in IMPORT_PROVIDERS.values()
    )


def import_provider_for(slug: str) -> ImportProvider:
    try:
        return IMPORT_PROVIDERS[slug]
    except KeyError as exc:
        raise KeyError(f"Unsupported import provider: {slug}") from exc


def import_provider_for_job_type(job_type: str) -> ImportProvider:
    for provider in IMPORT_PROVIDERS.values():
        if provider.job_type == job_type:
            return provider
    raise KeyError(f"No import provider registered for job type: {job_type}")
