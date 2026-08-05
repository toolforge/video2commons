#!/bin/bash

# Upgrades yt-dlp in the encoder venv.
#
# Celery is only restarted when the installed version actually changed, and the
# service is running (e.g. not restarting or manually stopped).

set -e

VENV_PIP=/srv/v2c/venv/bin/pip3

installed_version() {
    "$VENV_PIP" show yt-dlp | sed -n 's/^Version: //p'
}

before=$(installed_version)

"$VENV_PIP" install -U 'yt-dlp[default]'

after=$(installed_version)

if [ "$before" = "$after" ]; then
    echo "yt-dlp is already at $after, nothing to do"
    exit 0
fi

sub_state=$(systemctl show v2ccelery.service --property=SubState --value)

if [ "$sub_state" != "running" ]; then
    echo "yt-dlp went from '$before' to '$after', but skipping restart as celery is '$sub_state'"
    exit 0
fi

echo "yt-dlp went from '$before' to '$after', restarting celery"
systemctl --no-block restart v2ccelery.service
