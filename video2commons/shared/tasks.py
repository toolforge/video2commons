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

"""Helper functions for communicating with task websockets."""

import json
import traceback

from video2commons.shared.errors import normalize_error, format_exception


def get_task_hostname(conn, task_id):
    """Get the hostname of the worker processing a task from task ID."""
    hostname = conn.get("tasklock:" + task_id)

    # Old tasks don't have a hostname as the value in tasklock and store the
    # literal 'T' instead. Reinterpret these values as null.
    if hostname == "T":
        hostname = None

    return hostname.decode() if isinstance(hostname, bytes) else hostname


def get_task_title(conn, task_id):
    """Get task title from task ID."""
    title = conn.get("titles:" + task_id)

    return title.decode() if isinstance(title, bytes) else title


def get_task_status(conn, task_id):
    """Retrieve the status of a specific task."""
    # The Celery task class in the worker module needs to be imported
    # dynamically to prevent a cyclic reference.
    from video2commons.backend.worker import main

    title = get_task_title(conn, task_id)
    if not title:
        return None  # Task has been forgotten and results should be expired

    res = main.AsyncResult(task_id)
    task = {"id": task_id, "title": title, "hostname": get_task_hostname(conn, task_id)}

    try:
        state = res.state
    except Exception:
        task.update(
            {
                "status": "fail",
                "text": "The status of the task could not be retrieved.",
                "traceback": traceback.format_exc(),
            }
        )
    else:
        if state == "PENDING":
            task.update(
                {
                    "status": "progress",
                    "text": "Your task is pending...",
                    "progress": -1,
                }
            )
        elif state == "PROGRESS":
            task.update(
                {
                    "status": "progress",
                    "text": res.result["text"],
                    "progress": res.result["percent"],
                }
            )
        elif state == "SUCCESS":
            if isinstance(res.result, (list, tuple)):
                filename, wikifileurl = res.result
                task.update({"status": "done", "url": wikifileurl, "text": filename})
            elif isinstance(res.result, dict):
                if res.result["type"] == "done":
                    task.update(
                        {
                            "status": "done",
                            "url": res.result["url"],
                            "text": res.result["filename"],
                        }
                    )
        elif state == "FAILURE":
            e = res.result
            text = format_exception(e) if e else res.traceback
            normalized_error = (normalize_error(text) or {}) if text else {}

            task.update(
                {
                    "status": "fail",
                    "text": text,
                    "i18n_key": normalized_error.get("i18n_key"),
                    "i18n_urls": normalized_error.get("urls"),
                    "reportable": normalized_error.get("reportable", False),
                    "restartable": (
                        not conn.exists("restarted:" + task_id)
                        and conn.exists("params:" + task_id)
                    ),
                }
            )
        elif state == "RETRY":
            task.update(
                {
                    "status": "progress",
                    "text": "Your task is being rescheduled...",
                    "progress": -1,
                }
            )
        elif state == "ABORTED":
            task.update({"status": "abort", "text": "Your task is being aborted..."})
        else:
            task.update(
                {
                    "status": "fail",
                    "text": (
                        "This task is in an unknown state. Please file an issue "
                        "in GitHub: <a></a>"
                    ),
                    "url": "https://github.com/toolforge/video2commons/issues",
                }
            )

    return task


def publish_notification(conn, ntype, data):
    """Publish a task change notification."""
    conn.publish("v2cnotif:" + ntype, json.dumps(data))
