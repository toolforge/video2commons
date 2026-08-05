#!/bin/bash

# Upgrades yt-dlp in the frontend venv.
#
# The webservice is only reloaded when the installed version actually changed.
# The reload happens through uwsgi's 'touch-reload' option, since the toolforge
# CLI is not usable from the job image.

set -e

VENV_PIP="$HOME/www/python/venv/bin/pip3"
RELOAD_TRIGGER="$HOME/www/python/reload"

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

echo "yt-dlp went from '$before' to '$after', reloading the webservice"
touch "$RELOAD_TRIGGER"
