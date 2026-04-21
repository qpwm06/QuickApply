from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler


def build_scheduler(
    refresh_callable: Callable[[], object],
    refresh_interval_minutes: int,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_callable,
        trigger="interval",
        minutes=refresh_interval_minutes,
        id="refresh-all-profiles",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
