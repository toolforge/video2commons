#! /bin/bash

WORKERS_RUNNING=$(/srv/v2c/venv/bin/python3 -m celery -A video2commons.backend.worker inspect ping -j |jq 'with_entries(select(.key | test ("celery[12]@'"$HOSTNAME"'"))) | length == 2')

if [ "$WORKERS_RUNNING" = "true" ]; then
    exit 0
else
    systemctl restart v2ccelery.service
    exit 1
fi
