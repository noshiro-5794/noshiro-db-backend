from celery import shared_task

from apps.sync.services.season_pipeline_service import season_pipeline_service
from apps.sync.services.season_rollover_service import season_rollover_service


@shared_task(soft_time_limit=5400, time_limit=6000)
def run_season_pipeline_task(
    *,
    max_items_per_source: int | None = None,
    evaluate: bool = False,
) -> dict:
    return season_pipeline_service.run(
        max_items_per_source=max_items_per_source,
        evaluate=evaluate,
    )


@shared_task(soft_time_limit=6000, time_limit=6600)
def check_season_rollover_task() -> dict:
    return season_rollover_service.run()
