"""One-transfer capabilities for downloading YouTube media on a user's computer.

The browser keeps its normal session and CSRF protection. The agent receives a
short-lived capability for one staging file, never a Commons or browser token.
"""

import hashlib
import hmac
import json
import math
import os
import re
import secrets
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
from uuid import uuid4

from flask import Blueprint, abort, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException

local_agent = Blueprint("local_agent", __name__)
PAIR_TTL = 10 * 60
TRANSFER_TTL = 6 * 60 * 60
MAX_SIZE = 5 * (1 << 30)
CHUNK_SIZE = 4_000_000
CC_LICENSE = "Creative Commons Attribution license (reuse allowed)"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
EXTENSIONS = {"webm", "mkv", "mp4", "m4a", "ogg", "opus"}


def connection():
    """Use the frontend's existing Redis database."""
    from video2commons.frontend.shared import redisconnection

    return redisconnection


def upload_path(filekey):
    from video2commons.frontend.upload import getpath

    return getpath(filekey)


def describe(info):
    """Build the usual description without fetching anything from YouTube."""
    from video2commons.frontend.urlextract import _extract_info

    return _extract_info(info)


def banned():
    from video2commons.frontend.shared import check_banned

    return check_banned()


def youtube_url(value):
    """Accept individual videos only; discard other URL parameters."""
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
        host = parsed.hostname
        if host == "youtu.be":
            video_id = parsed.path.strip("/")
        elif host in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtube-nocookie.com",
            "www.youtube-nocookie.com",
        }:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            else:
                match = re.fullmatch(r"/(?:shorts|embed|live|v)/([^/]+)/?", parsed.path)
                video_id = match[1] if match else ""
        else:
            raise ValueError
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        abort(400, "Enter a link to a single YouTube video.")
    return f"https://www.youtube.com/watch?v={video_id}"


def job_key(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404, "Transfer not found.")
    return "local-agent:job:" + job_id


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def pair_key(token):
    return "local-agent:pair:" + digest(token)


def bearer():
    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer ") or not re.fullmatch(
        r"[A-Za-z0-9_-]{43}", value[7:]
    ):
        abort(401, "Invalid or expired agent token.")
    return value[7:]


def get_job(job_id, agent=False):
    conn = connection()
    job = conn.hgetall(job_key(job_id))
    if not job:
        abort(410, "Transfer expired. Start again in video2commons.")
    if agent:
        if not hmac.compare_digest(job.get("agent_hash", ""), digest(bearer())):
            abort(401, "Invalid or expired agent token.")
        # Logout or expiry of the initiating browser session revokes the agent.
        owner = json.loads(conn.get("session:" + job["session"]) or "{}")
        if owner.get("username") != job["username"]:
            abort(401, "The browser session has ended. Start again in video2commons.")
    elif job["session"] != session.sid or job["username"] != session["username"]:
        abort(404, "Transfer not found.")
    return job


def agent_lock(job_id):
    # Reject unauthenticated traffic before allocating a Redis lock key.
    get_job(job_id, agent=True)
    return connection().lock(job_key(job_id) + ":lock", timeout=180, blocking_timeout=2)


def limit_body(maximum):
    # All agent requests set Content-Length. Reject unknown/oversized bodies
    # before Flask parses them, including on older deployed Flask versions.
    if request.content_length is None or request.content_length > maximum:
        abort(413, "Request body is too large or has no Content-Length.")


@local_agent.before_request
def browser_auth():
    if request.endpoint in {
        "local_agent.start",
        "local_agent.status",
        "local_agent.cancel",
    }:
        if "username" not in session:
            abort(401, "Please log in to video2commons.")
        token = session.get("_csrf_token")
        if not token or token != request.form.get("_csrf_token"):
            abort(403, "Invalid CSRF token. Reload this page.")


@local_agent.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@local_agent.errorhandler(HTTPException)
def api_error(error):
    return jsonify(error=error.description), error.code


@local_agent.route("/download")
def download():
    return send_file(
        Path(__file__).with_name("desktop_agent.py"),
        as_attachment=True,
        download_name="video2commons-agent.py",
        mimetype="text/x-python",
    )


def discard(job_id):
    conn = connection()
    with conn.lock(job_key(job_id) + ":lock", timeout=180, blocking_timeout=2):
        job = conn.hgetall(job_key(job_id))
        if not job:
            return
        conn.delete(job_key(job_id), job["pair_key"])
        # Ready files may already be queued for conversion; normal upload cleanup
        # owns them from this point on.
        if job.get("filekey") and job["state"] != "ready":
            Path(upload_path(job["filekey"])).unlink(missing_ok=True)


@local_agent.route("/start", methods=["POST"])
def start():
    if banned():
        abort(403, "You are banned from using this tool.")
    url = youtube_url(request.form.get("url", ""))
    video = request.form.get("video") == "true"
    audio = request.form.get("audio") == "true"
    if not video and not audio:
        abort(400, "Keep at least one video or audio track.")
    previous = session.get("local_agent_job")
    if previous:
        discard(previous)
    job_id = uuid4().hex
    code = secrets.token_urlsafe(32)
    conn = connection()
    with conn.pipeline() as pipe:
        pipe.hset(
            job_key(job_id),
            mapping={
                "session": session.sid,
                "username": session["username"],
                "url": url,
                "video": str(int(video)),
                "audio": str(int(audio)),
                "state": "waiting",
                "pair_key": pair_key(code),
            },
        )
        pipe.expire(job_key(job_id), TRANSFER_TTL)
        pipe.set(pair_key(code), job_id, ex=PAIR_TTL)
        pipe.execute()
    session["local_agent_job"] = job_id
    return jsonify(id=job_id, code=code, expires_in=PAIR_TTL)


@local_agent.route("/status", methods=["POST"])
def status():
    job = get_job(request.form.get("id", ""))
    if job["state"] == "waiting" and not connection().exists(job["pair_key"]):
        abort(410, "Pairing code expired. Cancel and start again.")
    result = {"state": job["state"], "error": job.get("error", "")}
    if job.get("size"):
        result["percent"] = round(100 * int(job.get("offset", 0)) / int(job["size"]))
    if job["state"] == "ready":
        result["metadata"] = {
            **json.loads(job["description"]),
            "url": "uploads:" + job["filekey"],
            "extractor": "(uploads)",
            "type": "single",
            "video": job["video"] == "1",
            "audio": job["audio"] == "1",
            "subtitles": False,
            # Raw files can still need substantial server-side transcoding.
            "queue": "heavy",
        }
    return jsonify(**result)


@local_agent.route("/cancel", methods=["POST"])
def cancel():
    job_id = request.form.get("id", "")
    get_job(job_id)
    discard(job_id)
    return jsonify(cancelled=True)


@local_agent.route("/claim", methods=["POST"])
def claim():
    conn = connection()
    job_id = conn.getdel(pair_key(bearer()))
    if not job_id:
        abort(401, "Invalid, already used or expired pairing code.")
    with conn.lock(job_key(job_id) + ":lock", timeout=180, blocking_timeout=2):
        job = conn.hgetall(job_key(job_id))
        owner = json.loads(conn.get("session:" + job.get("session", "")) or "{}")
        if (
            not job
            or job["state"] != "waiting"
            or owner.get("username") != job["username"]
        ):
            abort(410, "The transfer or browser session has ended.")
        token = secrets.token_urlsafe(32)
        conn.hset(
            job_key(job_id),
            mapping={"agent_hash": digest(token), "state": "downloading"},
        )
    return jsonify(
        id=job_id,
        token=token,
        url=job["url"],
        video=job["video"] == "1",
        audio=job["audio"] == "1",
        max_size=MAX_SIZE,
        chunk_size=CHUNK_SIZE,
    )


def clean_metadata(data, url):
    """Treat local metadata as untrusted; never accept remote download URLs."""
    raw = data.get("metadata")
    if (
        not isinstance(raw, dict)
        or raw.get("id") != parse_qs(urlsplit(url).query)["v"][0]
    ):
        abort(400, "Metadata does not match the selected video.")
    if raw.get("license") != CC_LICENSE:
        abort(400, "The video must have a Creative Commons Attribution license.")
    info = {"formats": [], "extractor_key": "Youtube", "webpage_url": url}
    for field in (
        "id",
        "title",
        "description",
        "uploader",
        "uploader_url",
        "upload_date",
        "license",
    ):
        value = raw.get(field) or ""
        if not isinstance(value, str) or len(value) > 20000:
            abort(400, "Invalid video metadata.")
        info[field] = value
    try:
        uploader_url = urlsplit(info["uploader_url"])
    except ValueError:
        abort(400, "Invalid uploader URL.")
    if uploader_url.scheme not in {"http", "https"} or uploader_url.hostname not in {
        "www.youtube.com",
        "youtube.com",
        "m.youtube.com",
    }:
        info["uploader_url"] = ""
    else:
        # This URL is embedded in wikitext by the attribution helper.
        info["uploader_url"] = "https://www.youtube.com" + quote(
            uploader_url.path, safe="/@%"
        )
    for field in ("width", "height", "tbr", "vbr"):
        value = raw.get(field)
        if value is not None:
            if (
                not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                abort(400, "Invalid video metadata.")
            info[field] = value
    return info


@local_agent.route("/<job_id>/begin", methods=["POST"])
def begin(job_id):
    limit_body(100000)
    conn = connection()
    with agent_lock(job_id):
        job = get_job(job_id, agent=True)
        if job["state"] == "uploading":
            return jsonify(offset=int(job["offset"]))
        if job["state"] != "downloading":
            abort(409, "Transfer is not accepting a file.")
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400, "Expected a JSON object.")
        size = data.get("size")
        ext = data.get("extension")
        if (
            type(size) is not int
            or not 0 < size <= MAX_SIZE
            or not isinstance(ext, str)
            or ext not in EXTENSIONS
        ):
            abort(400, "Invalid file type or file size (maximum 5 GiB).")
        description = describe(clean_metadata(data, job["url"]))
        filekey = str(uuid4()) + "." + ext
        with open(upload_path(filekey), "xb"):
            pass
        conn.hset(
            job_key(job_id),
            mapping={
                "state": "uploading",
                "filekey": filekey,
                "size": size,
                "offset": 0,
                "description": json.dumps(description),
            },
        )
    return jsonify(offset=0)


@local_agent.route("/<job_id>/chunk", methods=["POST"])
def chunk(job_id):
    limit_body(CHUNK_SIZE)
    conn = connection()
    with agent_lock(job_id):
        job = get_job(job_id, agent=True)
        if job["state"] != "uploading":
            abort(409, "Transfer is not accepting a file.")
        match = re.fullmatch(
            r"bytes (\d+)-(\d+)/(\d+)", request.headers.get("Content-Range", "")
        )
        if not match:
            abort(400, "Invalid Content-Range.")
        start, end, total = map(int, match.groups())
        if (
            total != int(job["size"])
            or not 0 <= start <= end < total
            or end - start + 1 > CHUNK_SIZE
        ):
            abort(400, "Invalid chunk size or range.")
        path = upload_path(job["filekey"])
        offset = os.path.getsize(path)
        # Retrying a chunk after a lost response never appends it twice.
        if start != offset:
            return jsonify(offset=offset)
        data = request.get_data(cache=False)
        if len(data) != end - start + 1:
            abort(400, "Chunk length does not match Content-Range.")
        with open(path, "ab") as dest:
            try:
                dest.write(data)
                dest.flush()
            except OSError:
                dest.truncate(offset)
                raise
        offset += len(data)
        conn.hset(job_key(job_id), "offset", offset)
    return jsonify(offset=offset)


@local_agent.route("/<job_id>/complete", methods=["POST"])
def complete(job_id):
    conn = connection()
    with agent_lock(job_id):
        job = get_job(job_id, agent=True)
        if job["state"] == "ready":
            return jsonify(ready=True)
        if job["state"] != "uploading" or os.path.getsize(
            upload_path(job["filekey"])
        ) != int(job["size"]):
            abort(409, "The file has not finished uploading.")
        conn.hset(job_key(job_id), "state", "ready")
    return jsonify(ready=True)


@local_agent.route("/<job_id>/error", methods=["POST"])
def report_error(job_id):
    limit_body(10000)
    conn = connection()
    with agent_lock(job_id):
        job = get_job(job_id, agent=True)
        if job["state"] != "ready":
            data = request.get_json()
            if not isinstance(data, dict):
                abort(400, "Expected a JSON object.")
            error = str(data.get("error", "Local download failed."))[:2000]
            conn.hset(job_key(job_id), mapping={"state": "error", "error": error})
    return jsonify(received=True)
