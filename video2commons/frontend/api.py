#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2015-2016 Zhuyifei1999
#
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>`
#

"""video2commons web API."""

import json
import os
import traceback
import re

from uuid import uuid4

from flask import Blueprint, request, session, jsonify, current_app

from video2commons.config import session_key

from video2commons.backend import worker

from video2commons.frontend.shared import (
    redisconnection,
    check_banned,
    generate_csrf_token,
    redis_publish,
)
from video2commons.frontend.urlextract import (
    do_extract_url,
    do_validate_filename_unique,
    do_validate_youtube_id,
    make_dummy_desc,
    do_validate_filename,
    do_validate_filedesc,
    sanitize,
    DEFAULT_QUEUE,
    HEAVY_QUEUE,
)
from video2commons.frontend.upload import upload as _upload, status as _uploadstatus
from video2commons.shared import stats

# Adapted from: https://stackoverflow.com/a/19161373
YOUTUBE_REGEX = (
    r"(https?://)?(www\.)?"
    r"(youtube|youtu|youtube-nocookie)\.(com|be)/"
    r"(watch\?.*?(?=v=)v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
)

FILEKEY_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "static/uploads"
)

VALID_QUEUES = {DEFAULT_QUEUE, HEAVY_QUEUE}

api = Blueprint("api", __name__)


@api.errorhandler(Exception)
def all_exception_handler(e):
    """Handle an exception and return an error JSON responce."""
    return error_json(e)


@api.before_request
def check_logged_in():
    """Error if a user is not logged in."""
    if (
        "username" not in session
        and request.headers.get("X-V2C-Session-Bypass") != session_key
    ):
        return error_json("Are you logged in?")


@api.before_request
def csrf_protect():
    """For POSTs, require CSRF token."""
    if request.method == "POST":
        token = session.get("_csrf_token")
        if not token or token != request.form.get("_csrf_token"):
            return error_json("Invalid CSRF token. Try reloading this page.")


def format_exception(e):
    """Format an exception to text."""
    desc = str(e)[:7000]

    if isinstance(e, AssertionError):
        return desc
    else:
        return f"An exception occurred: {type(e).__name__}: {desc}"


def error_json(e):
    """Get a JSON responce on error."""
    session.rollback()
    if isinstance(e, BaseException):
        return jsonify(
            step="error", error=format_exception(e), traceback=traceback.format_exc()
        )
    else:
        return jsonify(step="error", error=e, traceback=None)


@api.route("/csrf")
def get_csrf():
    """Get the CSRF token for API-only access."""
    return jsonify(csrf=generate_csrf_token())


@api.route("/iosession")
def get_iosession():
    """Get a pointer to session for read-only socket.io notifications."""
    iosession = str(uuid4())
    redisconnection.set("iosession:" + iosession, session.sid)
    redisconnection.expire("iosession:" + iosession, 60)
    return jsonify(iosession=iosession)


@api.route("/status")
def status():
    """Get all visible task status for user."""
    key, ids = get_tasks()
    values = []
    for id in ids:
        values.append(_status(id))

    values = [_f for _f in values if _f]
    rooms = [t["id"] for t in values] + [key]
    return jsonify(
        values=values, rooms=rooms, username=session["username"], stats=get_stats()
    )


@api.route("/status-single")
def status_single():
    """Get the status of one task."""
    return jsonify(value=_status(request.args["task"]))


def _status(id):
    title = get_title_from_task(id)
    if not title:
        # task has been forgotten -- results should have been expired
        return None

    res = worker.main.AsyncResult(id)
    task = {"id": id, "title": title, "hostname": get_hostname_from_task(id)}

    try:
        state = res.state
    except:
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
                elif res.result["type"] == "ssu":
                    task.update(
                        {
                            "status": "needssu",
                            "filename": res.result["url"].rsplit("/", 1)[-1],
                            "url": res.result["url"],
                            "hashsum": res.result["hashsum"],
                        }
                    )
        elif state == "FAILURE":
            e = res.result
            if e is False:
                task.update(
                    {"status": "fail", "text": res.traceback, "restartable": True}
                )
            else:
                task.update(
                    {
                        "status": "fail",
                        "text": format_exception(e),
                        "restartable": (
                            (not redisconnection.exists("restarted:" + id))
                            and redisconnection.exists("params:" + id)
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


def is_sudoer(username):
    """Check if a user is a sudoer."""
    return username in redisconnection.lrange("sudoers", 0, -1)


def get_tasks():
    """Get a list of visible tasks for user."""
    # sudoer = able to monitor all tasks
    username = session["username"]
    if session.get("is_maintainer"):
        key = "alltasks"
    else:
        key = "tasks:" + username

    return key, redisconnection.lrange(key, 0, -1)[::-1]


def get_stats():
    """Get worker stats from Redis."""
    stats = redisconnection.get("stats")

    return json.loads(stats) if stats else None


def get_title_from_task(id):
    """Get task title from task ID."""
    return redisconnection.get("titles:" + id)


def get_hostname_from_task(id):
    """Get the hostname of the worker processing a task from task ID."""
    hostname = redisconnection.get("tasklock:" + id)

    # Old tasks don't have a hostname as the value in tasklock and store the
    # literal 'T' instead. Reinterpret these values as null.
    if hostname == "T":
        hostname = None

    return hostname


@api.route("/extracturl", methods=["POST"])
def extract_url():
    """Extract a video url."""
    url = request.form["url"]

    return jsonify(**do_extract_url(url))


@api.route("/makedesc", methods=["POST"])
def make_desc():
    """Create a (mostly-empty) description."""
    filename = request.form["filename"]

    return jsonify(**make_dummy_desc(filename))


@api.route("/listformats", methods=["POST"])
def list_formats():
    """List the possible convert formats from a given audio/video pair."""
    formats = []
    prefer = ""
    video = _boolize(request.form["video"])
    audio = _boolize(request.form["audio"])
    if video:
        if audio:
            formats = [
                "ogv (Theora/Vorbis)",
                "webm (VP8/Vorbis)",
                "webm (VP9/Opus)",
                "webm (AV1/Opus)",
            ]
            prefer = "webm (AV1/Opus)"
        else:
            formats = ["ogv (Theora)", "webm (VP8)", "webm (VP9)", "webm (AV1)"]
            prefer = "webm (AV1)"
    else:
        if audio:
            formats = ["ogg (Vorbis)", "opus (Opus)"]
            prefer = "ogg (Vorbis)"
        else:
            raise RuntimeError("Either video or audio must be kept")

    return jsonify(audio=audio, video=video, format=prefer, formats=formats)


def _boolize(data):
    return data in [True, "true", "TRUE", "True", 1, "1"]


@api.route("/validatefilename", methods=["POST"])
def validate_filename():
    """Validate filename for invalid characters/parts."""
    return jsonify(filename=do_validate_filename(request.form["filename"]))


@api.route("/validatefiledesc", methods=["POST"])
def validate_filedesc():
    """Validate filename for invalid characters/parts."""
    return jsonify(filedesc=do_validate_filedesc(request.form["filedesc"]))


@api.route("/validatefilenameunique", methods=["POST"])
def validate_filename_unique():
    """Validate filename isn't already in use on the wiki."""
    return jsonify(filename=do_validate_filename_unique(request.form["filename"]))


@api.route("/validateurl", methods=["POST"])
def validate_url():
    """Validate that a video belonging to a URL is not already on the wiki."""
    url = request.form["url"]

    # Check if the URL is a YouTube URL, and if so, extract the ID and validate
    # that it doesn't already exist on Commons.
    yt_match = re.match(YOUTUBE_REGEX, url)
    if yt_match:
        try:
            youtube_id = yt_match.group(6)
            return jsonify(entity_url=do_validate_youtube_id(youtube_id))
        except Exception as e:
            current_app.logger.error(
                f'Error validating YouTube URL "{url}": {e}\n\n{traceback.format_exc()}'
            )

            # Skip validation if errors are encountered, e.g. SPARQL is down.
            return jsonify(entity_url=None)

    return jsonify(entity_url=None)


def get_backend_keys(format):
    """Get the youtube-dl download format key."""

    MAXSIZE = 5 << 30
    COMBINED_FMT = (
        "bestvideo[filesize<{max}]+"
        "bestaudio[acodec={{acodec}}]/"
        "bestvideo[filesize<{max}]+"
        "bestaudio[ext={{aext}}]/"
        "bestvideo+bestaudio/best"
    ).format(max=MAXSIZE)
    VIDEO_FMT = ("bestvideo[filesize<{max}]/bestvideo/best").format(max=MAXSIZE)
    AUDIO_FMT = (
        "bestaudio[acodec={{acodec}}]/bestaudio[ext={{aext}}]/bestaudio/best"
    ).format()
    return {
        "ogv (Theora)": (VIDEO_FMT.format(vcodec="theora", vext="ogv"), "an.ogv"),
        "webm (VP8)": (VIDEO_FMT.format(vcodec="vp8", vext="webm"), "an.webm"),
        "webm (VP9)": (VIDEO_FMT.format(vcodec="vp9", vext="webm"), "an.vp9.webm"),
        "webm (AV1)": (VIDEO_FMT.format(vcodec="av1", vext="webm"), "an.av1.webm"),
        "ogg (Vorbis)": (AUDIO_FMT.format(acodec="vorbis", aext="ogg"), "ogg"),
        "opus (Opus)": (AUDIO_FMT.format(acodec="opus", aext="opus"), "opus"),
        "ogv (Theora/Vorbis)": (
            COMBINED_FMT.format(
                vcodec="theora", vext="ogv", acodec="vorbis", aext="ogg"
            ),
            "ogv",
        ),
        "webm (VP8/Vorbis)": (
            COMBINED_FMT.format(vcodec="vp8", vext="webm", acodec="vorbis", aext="ogg"),
            "webm",
        ),
        "webm (VP9/Opus)": (
            COMBINED_FMT.format(vcodec="vp9", vext="webm", acodec="opus", aext="webm"),
            "vp9.webm",
        ),
        "webm (AV1/Opus)": (
            COMBINED_FMT.format(vcodec="av1", vext="webm", acodec="opus", aext="webm"),
            "av1.webm",
        ),
    }[format]


@api.route("/task/run", methods=["POST"])
def run_task():
    """Run a task with parameters from session."""
    url = request.form["url"]
    ie_key = request.form["extractor"]
    subtitles = request.form["subtitles"]
    filename = sanitize(request.form["filename"])
    filedesc = request.form["filedesc"]
    downloadkey, convertkey = get_backend_keys(request.form["format"])
    username = session["username"]
    oauth = (session["access_token_key"], session["access_token_secret"])
    queue = request.form.get("queue")

    # If no queue is specified, such is the case with manually uploaded files
    # due to yt-dlp not being used and extracturl not being called, determine
    # which queue to process the file on based on file metadata such as bitrate
    # and resolution. We do this to avoid OOM errors with heavy files.
    if not queue:
        if url.startswith("uploads:"):
            filekey = url.split(":", 1)[1]
            if not FILEKEY_REGEX.match(filekey):
                return jsonify(error="Invalid file key format"), 400

            # Hotfix: Temporarily default to DEFAULT_QUEUE until the ffprobe
            # issue is properly fixed.
            queue = DEFAULT_QUEUE

            # filepath = os.path.join(UPLOADS_DIR, filekey)
            # queue = predict_task_type_ffprobe(filepath)
        else:
            queue = DEFAULT_QUEUE

    taskid = run_task_internal(
        filename,
        (
            url,
            ie_key,
            subtitles,
            filename,
            filedesc,
            downloadkey,
            convertkey,
            username,
            oauth,
        ),
        queue,
    )

    return jsonify(id=taskid, step="success")


def run_task_internal(filename, params, queue):
    """Internal run task function to accept whatever params given."""
    banned = check_banned()
    assert not banned, "You are banned from using this tool! Reason: " + banned

    # Validate queue to prevent tasks being sent to non-existent queues.
    # Unfortunately Celery tries to be helpful and creates queues on demand.
    if queue not in VALID_QUEUES:
        queue = DEFAULT_QUEUE

    res = worker.main.apply_async(args=params, queue=queue)
    taskid = res.id

    expire = 14 * 24 * 3600  # 2 weeks
    redisconnection.lpush("alltasks", taskid)
    redisconnection.expire("alltasks", expire)
    redisconnection.lpush("tasks:" + session["username"], taskid)
    redisconnection.expire("tasks:" + session["username"], expire)
    redisconnection.set("titles:" + taskid, filename)
    redisconnection.expire("titles:" + taskid, expire)
    redisconnection.set("params:" + taskid, json.dumps(params))
    redisconnection.expire("params:" + taskid, expire)

    try:
        stats.increment_queue_counter(redisconnection)
    except Exception:
        pass  # We don't want to fail the API call if we can't update stats.

    redis_publish("add", {"taskid": taskid, "user": session["username"]})
    redis_publish("update", {"taskid": taskid, "data": _status(taskid)})

    return taskid


@api.route("/task/restart", methods=["POST"])
def restart_task():
    """Reastart a task: run a task with params of another task."""
    id = request.form["id"]

    filename = redisconnection.get("titles:" + id)
    assert filename, "Task does not exist"
    if not session.get("is_maintainer"):
        assert id in redisconnection.lrange("tasks:" + session["username"], 0, -1), (
            "Task must belong to you."
        )

    restarted = redisconnection.get("restarted:" + id)
    assert not restarted, "Task has already been restarted with id " + restarted
    params = redisconnection.get("params:" + id)
    assert params, "Could not extract the task parameters."

    # Always restart failed tasks on the heavy queue as a failsafe in case the
    # task failed earlier due to being misprioritized.
    newid = run_task_internal(filename, json.loads(params), HEAVY_QUEUE)
    redisconnection.set("restarted:" + id, newid)

    redis_publish("update", {"taskid": id, "data": _status(id)})

    return jsonify(restart="success", id=id, taskid=newid)


@api.route("/task/remove", methods=["POST"])
def remove_task():
    """Revove a task from list of tasks."""
    id = request.form["id"]
    username = session["username"]
    if not session.get("is_maintainer"):
        assert id in redisconnection.lrange("tasks:" + username, 0, -1), (
            "Task must belong to you."
        )
    redisconnection.lrem("alltasks", 0, id)
    redisconnection.lrem("tasks:" + username, 0, id)
    redisconnection.delete("titles:" + id)
    redisconnection.delete("params:" + id)
    redisconnection.delete("restarted:" + id)

    redis_publish("remove", {"taskid": id})

    return jsonify(remove="success", id=id)


@api.route("/task/abort", methods=["POST"])
def abort_task():
    """Abort a task."""
    id = request.form["id"]
    username = session["username"]
    if not session.get("is_maintainer"):
        assert id in redisconnection.lrange("tasks:" + username, 0, -1), (
            "Task must belong to you."
        )
    worker.main.AsyncResult(id).abort()

    redis_publish("update", {"taskid": id, "data": _status(id)})

    return jsonify(remove="success", id=id)


# No nested blueprints in flask; we have to do this :(
@api.route("/upload/upload", methods=["POST"])
def upload():
    return _upload()


@api.route("/upload/status", methods=["POST"])
def uploadstatus():
    return _uploadstatus()
