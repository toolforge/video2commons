#!/bin/bash
#
# Health check for the celery service of an encoder.
#
# Usage: healthcheck.sh [--check]
#
# Without arguments (cron, as root) the service is repaired when needed:
#   - stopped or failed              -> restarted
#   - started but not answering ping -> restarted (warm: running tasks finish)
#   - stuck in "deactivating" after its main process is gone (e.g. orphaned
#     ffmpeg processes after an OOM kill) -> everything is killed with SIGKILL,
#     systemd then restarts the service
#
# With --check nothing is modified, the status is printed and reflected in the
# exit code:
#   0  healthy
#   10 draining: stopping gracefully, waiting for running tasks to finish
#   11 stuck: see above
#   1  anything else (starting, down, not answering)

set -u

# Provides CELERYD_NODES, CELERY_BIN and CELERY_APP.
# shellcheck source=/dev/null
[ -r /etc/default/v2ccelery ] && . /etc/default/v2ccelery

SERVICE=v2ccelery.service
SERVICE_USER=tools.video2commons
CELERY_BIN=${CELERY_BIN:-/srv/v2c/venv/bin/celery}
CELERY_APP=${CELERY_APP:-video2commons.backend.worker}
EXPECTED_NODES=${CELERYD_NODES:-1}
STUCK_STOP_SECS=${STUCK_STOP_SECS:-900}
PING_ATTEMPTS=3

MODE=repair
if [ "${1:-}" = "--check" ]; then
    MODE=check
    PING_ATTEMPTS=1
fi

HOST=$(hostname)

log() {
    logger -t v2c-healthcheck "$*"
    echo "$*"
}

show() {
    systemctl show "$SERVICE" --property="$1" --value
}

# Number of celery nodes of this host that answer to a ping.
responding_nodes() {
    local out
    out=$(cd /srv/v2c && runuser -u "$SERVICE_USER" -- "$CELERY_BIN" \
        -A "$CELERY_APP" inspect ping -t 10 -j 2>/dev/null) || return 1
    printf '%s' "$out" | jq --arg host "$HOST" \
        '[keys[] | select(test("^celery[0-9]+@" + $host + "$"))] | length' 2>/dev/null
}

is_responding() {
    local attempt nodes
    for attempt in $(seq 1 "$PING_ATTEMPTS"); do
        nodes=$(responding_nodes)
        if [ "${nodes:-0}" -ge "$EXPECTED_NODES" ]; then
            return 0
        fi
        [ "$attempt" -lt "$PING_ATTEMPTS" ] && sleep 5
    done
    return 1
}

# Seconds spent in the current state of the unit.
state_age() {
    local since_us uptime_s
    since_us=$(show StateChangeTimestampMonotonic)
    uptime_s=$(cut -d. -f1 /proc/uptime)
    echo $((uptime_s - since_us / 1000000))
}

# Prints one of: healthy, starting, draining, stuck, down, unresponsive
service_status() {
    case "$(show ActiveState)" in
        active)
            if is_responding; then echo healthy; else echo unresponsive; fi
            ;;
        activating)
            echo starting
            ;;
        deactivating)
            if [ "$(show MainPID)" != "0" ]; then
                echo draining
            elif [ "$(state_age)" -ge "$STUCK_STOP_SECS" ]; then
                echo stuck
            else
                echo starting
            fi
            ;;
        *)
            echo down
            ;;
    esac
}

status=$(service_status)

if [ "$MODE" = "check" ]; then
    echo "$SERVICE: $status"
    case "$status" in
        healthy) exit 0 ;;
        draining) exit 10 ;;
        stuck) exit 11 ;;
        *) exit 1 ;;
    esac
fi

case "$status" in
    healthy | starting | draining)
        exit 0
        ;;
    stuck)
        log "$SERVICE is stuck while stopping, killing all its processes"
        systemctl kill --kill-whom=all --signal=SIGKILL "$SERVICE"
        exit 1
        ;;
    *)
        log "$SERVICE is $status, restarting"
        systemctl --no-block restart "$SERVICE"
        exit 1
        ;;
esac
