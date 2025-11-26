"""Utility functions for getting statistics about the worker pool."""

import json
import time

LOCK_KEY = 'stats_lock'


def collect_worker_stats(conn, inspector):
    """Collect usage statistics of all active workers."""
    stats = inspector.stats()
    total_capacity = 0

    if stats:
        for _, worker_stats in stats.items():
            pool = worker_stats.get('pool', {})
            max_concurrency = pool.get('max-concurrency', 0)
            total_capacity += max_concurrency

    active_tasks = inspector.active()
    total_active = 0
    task_ids = []

    if active_tasks:
        for _, tasks in active_tasks.items():
            total_active += len(tasks)

            for task in tasks:
                task_id = task.get('id')
                if task_id:
                    task_ids.append(task_id)

    queue_length = get_queue_length(conn)

    return {
        'task_ids': task_ids,
        'pending': queue_length,
        'capacity': total_capacity,
        'processing': total_active,
        'available': total_capacity - total_active,
        'utilization': (total_active / total_capacity) if total_capacity > 0 else 0,
        'last_updated_by_job': int(time.time()),
    }


def get_queue_length(conn):
    """Get the number of messages waiting in the broker queue."""
    return conn.llen('celery') + conn.hlen('unacked')


def update_task_stats(conn, task_id, remove=False):
    """Update worker stats in Redis."""
    # Try to acquire lock with retries (up to ~1 second total).
    lock_acquired = acquire_write_lock(conn)
    if not lock_acquired:
        raise RuntimeError("Could not acquire write lock on stats key.")

    try:
        serialized_stats = conn.get('stats')
        if not serialized_stats:
            raise RuntimeError("No stats are available, aborting.")

        stats = json.loads(serialized_stats)

        if not remove:
            stats['task_ids'].append(task_id)
        else:
            # This can fail with a ValueError, but that's fine since we don't
            # want to write to the key if this happens anyway.
            stats['task_ids'].remove(task_id)

        stats['processing'] = len(stats['task_ids'])
        stats['available'] = stats['capacity'] - stats['processing']
        stats['utilization'] = (stats['processing'] / stats['capacity']) if stats['capacity'] > 0 else 0

        # Update the queued tasks counter, which only tracks tasks that haven't
        # been picked up by any workers yet.
        if not remove:
            stats['pending'] = max(stats['pending'] - 1, 0)

        # FAILSAFE: We shouldn't get weird numbers in stats, but be safe.
        if (
            stats['available'] > stats['capacity']
            or stats['available'] < 0
            or stats['processing'] > stats['capacity']
            or stats['processing'] < 0
        ):
            raise RuntimeError("Received invalid stats, aborting.")

        update_worker_stats(conn, stats)
    finally:
        release_write_lock(conn)


def increment_queue_counter(conn):
    """Increment the queued tasks counter in Redis."""
    # Try to acquire lock with retries (up to ~1 second total).
    lock_acquired = acquire_write_lock(conn)
    if not lock_acquired:
        raise RuntimeError("Could not acquire write lock on stats key.")

    try:
        serialized_stats = conn.get('stats')
        if not serialized_stats:
            raise RuntimeError("No stats are available, aborting.")

        stats = json.loads(serialized_stats)
        stats['pending'] = stats.get('pending', 0) + 1

        update_worker_stats(conn, stats)
    finally:
        release_write_lock(conn)


def acquire_write_lock(conn):
    """Acquire a write lock on the stats key (~1 second timeout)."""
    for _ in range(10):
        try:
            lock_acquired = conn.set(LOCK_KEY, '1', nx=True, ex=2)
            if lock_acquired:
                return True
        except Exception:
            return False

        time.sleep(0.1)

    return False


def release_write_lock(conn):
    """Release the write lock on the stats key."""
    try:
        conn.delete(LOCK_KEY)
    except Exception:
        pass


def get_worker_stats(conn):
    """Get worker stats from Redis."""
    serialized_stats = conn.get('stats')
    if not serialized_stats:
        return None

    return json.loads(serialized_stats)


def update_worker_stats(conn, stats):
    """Update worker stats in Redis."""
    conn.set('stats', json.dumps(stats))
