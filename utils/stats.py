#!/usr/bin/env python3

"""Update worker usage and capacity statistics in Redis."""

import random
import sys
import time

sys.path.insert(0, '/srv/v2c')

from redis import Redis

from video2commons.backend.worker import app as celery_app
from video2commons.config import redis_pw, redis_host
from video2commons.shared.stats import (
    acquire_write_lock,
    collect_worker_stats,
    get_worker_stats,
    release_write_lock,
    update_worker_stats
)

# Stats are considered stale if they haven't been updated in 30 minutes.
STALE_SECS = 1800

# Add some sleep between 0 seconds and 5 minutes to avoid hammering the workers.
SLEEP_RANGE = (0, 300)

queue_conn = Redis(host=redis_host, password=redis_pw, db=2)
app_conn = Redis(host=redis_host, password=redis_pw, db=3)


def main():
    sleep_secs = random.randint(*SLEEP_RANGE)
    print(f"Sleeping for {sleep_secs} seconds...")

    # This job is run on workers to allow connecting directly to the workers,
    # but we don't want to hammer them with duplicate requests. Sleep a random
    # amount and check if the stats have been updated recently to avoid this.
    time.sleep(sleep_secs)

    # Don't update stats if they've been updated recently by another job.
    existing_stats = get_worker_stats(app_conn)
    if existing_stats and 'last_updated_by_job' in existing_stats:
        if int(time.time()) - existing_stats['last_updated_by_job'] < STALE_SECS:
            print("Stats have been updated recently, skipping update.")
            return

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
