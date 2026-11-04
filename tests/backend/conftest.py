"""Make the backend importable without an encoder's configuration."""

import os

# The worker logs in to Commons only when a task runs, and the tests replace
# the Site with a fake one.
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")

from video2commons import config

# config.json only exists on the servers. The worker needs these values to be
# strings when it is imported, but never connects to anything during tests.
for name in ("consumer_key", "consumer_secret", "redis_host", "redis_pw"):
    if getattr(config, name) is None:
        setattr(config, name, "test")
