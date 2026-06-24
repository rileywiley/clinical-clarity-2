"""arq worker (Phase 5).

Single worker class, one job (``parse_soa``). Started by
``arq app.worker.WorkerSettings`` in docker-compose.
"""

from arq.connections import RedisSettings

from app.config import get_settings
from app.worker.soa_parser import parse_soa


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """arq picks this up as ``app.worker.WorkerSettings``."""

    functions = [parse_soa]
    redis_settings = _redis_settings()
    # Jobs aren't time-critical and the SoA parse can take 30-60s — give it
    # room. arq retries on failure by default; we let it.
    job_timeout = 300
    max_jobs = 4


__all__ = ["WorkerSettings", "parse_soa"]
