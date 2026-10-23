# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>

"""Helpers for distributed rate limiting of yt-dlp requests."""

import logging
from contextlib import contextmanager
from urllib.parse import urlparse

import yt_dlp
from redis import Redis
from redis.exceptions import LockError, LockNotOwnedError
from redis.lock import Lock

logger = logging.getLogger(__name__)

# Redis key prefix for rate limit locks.
LOCK_KEY_PREFIX = "yt_dlp_lock"

# Default lock timeout in seconds. 20 minutes was chosen to accommodate the
# cumulative sleep delays from rate limiting (e.g. 10s per media segment, 3s
# per extraction request), while still expiring in a reasonable time if a
# worker dies without releasing the lock.
DEFAULT_LOCK_TIMEOUT = 20 * 60

# Domains where rate limiting logic should be applied, grouped by site.
RATE_LIMITED_DOMAINS = {
    "youtube": {
        "youtube.com",
        "youtube-nocookie.com",
        "youtubekids.com",
        "youtu.be",
        "youtube.googleapis.com",
    },
}

# Rate limiting parameters for each type of request being made to YouTube.
# These are tweaked to work best with anonymous calls to YouTube that are made
# without session cookies.
SLEEP_PARAMS = {
    "sleep_interval": 10,  # Media file downloads (video/audio).
    "sleep_interval_requests": 3,  # Extraction requests (metadata, pages).
    "sleep_interval_subtitles": 6,  # Subtitle downloads.
}


@contextmanager
def YoutubeDLRateLimited(
    conn: Redis,
    source: str,
    url: str,
    params: dict | None = None,
    auto_init=True,
    timeout=DEFAULT_LOCK_TIMEOUT,
    blocking_timeout=DEFAULT_LOCK_TIMEOUT,
):
    """Wrapper around yt_dlp.YoutubeDL that applies distributed rate limiting.

    This context manager wraps yt-dlp's YoutubeDL class and automatically
    prevents multiple workers from downloading videos and metadata
    simultaneously based on the URL. This effectively reduces the risk of us
    being blocked by heavily rate-limited sites like YouTube.

    In addition to the existing YoutubeDL parameters, this context manager also
    requires that a Redis connection, source, and URL be provided. The source
    is the name of the app requesting a lock and is incorporated into the
    lock's key name. This allows a different lock to be used for the frontend
    than the backend workers.

    The URL is needed to allow different groups of sites to be ratelimited
    separately (or not at all). Currently, only YouTube is ratelimited.

    timeout controls how long the lock exists in Redis before auto-expiring.
    blocking_timeout controls how long to wait for the lock before giving up.
    """
    # Apply ratelimit parameters if the URL is from a ratelimited domain.
    group = _get_ratelimit_group(url)
    params = (SLEEP_PARAMS if group else {}) | (params or {})

    # Acquire the distributed lock before starting the download to prevent
    # multiple workers from downloading videos and metadata at the same time,
    # which can potentially cause sites like YouTube to block us.
    lock = None
    if group:
        lock = _acquire_lock(conn, source, group, timeout, blocking_timeout)

    try:
        with yt_dlp.YoutubeDL(params, auto_init=auto_init) as dl:
            yield dl
    finally:
        # Always release the lock regardless of success or failure.
        if lock:
            _release_lock(lock)


def _get_ratelimit_group(url: str) -> str | None:
    """Return the ratelimit group name for a URL if it's ratelimited."""
    if (hostname := urlparse(url).hostname) is None:
        return None

    hostname = hostname.lower()

    for group, domains in RATE_LIMITED_DOMAINS.items():
        if any(hostname == d or hostname.endswith("." + d) for d in domains):
            logger.debug("URL '%s' matched ratelimit group '%s'", url, group)
            return group

    return None


def _key(source: str, group: str):
    """Generate a lock key for the given source and domain group."""
    return f"{LOCK_KEY_PREFIX}:{source}:{group}"


def _acquire_lock(
    conn: Redis,
    source: str,
    group: str,
    timeout=DEFAULT_LOCK_TIMEOUT,
    blocking_timeout=DEFAULT_LOCK_TIMEOUT,
) -> Lock:
    """Acquire a distributed Redis lock."""
    key = _key(source, group)

    lock = conn.lock(
        name=key,
        timeout=timeout,
        blocking_timeout=blocking_timeout,
    )
    try:
        acquired = lock.acquire()
    except LockError:
        acquired = False

    if not acquired:
        message = "Failed to acquire lock '%s'"
        logger.error(message, key)
        raise RuntimeError(message % key)

    logger.info("Acquired lock '%s'", key)

    return lock


def _release_lock(lock: Lock):
    """Release a distributed Redis lock."""
    try:
        lock.release()
        logger.info("Released lock '%s'", lock.name)
    except LockNotOwnedError:
        logger.warning(
            "Lock '%s' expired before release (owned by another worker)",
            lock.name,
        )
    except LockError:
        message = "Failed to release lock '%s'"
        logger.error(message, lock.name)
