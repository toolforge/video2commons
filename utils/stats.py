#!/usr/bin/env python3

"""Update worker usage and capacity statistics in Redis."""

import sys

sys.path.insert(0, '/srv/v2c')

from redis import Redis

from video2commons.backend.worker import app as celery_app
from video2commons.config import redis_pw, redis_host
from video2commons.shared.stats import (
    acquire_write_lock,
    collect_worker_stats,
    release_write_lock,
    update_worker_stats
)

queue_conn = Redis(host=redis_host, password=redis_pw, db=2)
app_conn = Redis(host=redis_host, password=redis_pw, db=3)


def main():
    inspector = celery_app.control.inspect(timeout=5.0)
    stats = collect_worker_stats(queue_conn, inspector)

    lock_acquired = acquire_write_lock(app_conn)
    if not lock_acquired:
        raise RuntimeError("Failed to update stats, could not acquire lock.")

    try:
        update_worker_stats(app_conn, stats)
    finally:
        release_write_lock(app_conn)

if __name__ == '__main__':
    main()
