#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "yt-dlp[default]"]
# ///
"""Download one YouTube video locally and stage it for video2commons.

Install Python 3.10+, ffmpeg, requests and yt-dlp[default], then run this file.
Alternatively: uv run video2commons-agent.py
No browser cookies, passwords or Commons access tokens are requested or stored.
"""

import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
import yt_dlp

CC_LICENSE = "Creative Commons Attribution license (reuse allowed)"
METADATA_FIELDS = (
    "id",
    "title",
    "description",
    "uploader",
    "uploader_url",
    "upload_date",
    "license",
    "width",
    "height",
    "tbr",
    "vbr",
)


def parse_pairing(value):
    """The fragment is a one-use code, never part of an HTTP URL or query."""
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.port not in {None, 443}
        or parsed.hostname
        not in {
            "video2commons.toolforge.org",
            "video2commons-test.toolforge.org",
        }
        or parsed.path not in {"", "/"}
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", parsed.fragment)
    ):
        raise ValueError(
            "Paste the full pairing code from video2commons, including https:// and #."
        )
    return f"https://{parsed.hostname}", parsed.fragment


def post(http, server, endpoint, token, **kwargs):
    """Never follow redirects carrying an agent capability to another host."""
    response = http.post(
        server + "/api/local-agent/" + endpoint,
        headers={"Authorization": "Bearer " + token, **kwargs.pop("headers", {})},
        timeout=(15, 120),
        allow_redirects=False,
        **kwargs,
    )
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            f"video2commons returned HTTP {response.status_code}."
        ) from None
    if not response.ok or data.get("error"):
        raise RuntimeError(data.get("error") or f"HTTP {response.status_code}")
    return data


def retry_post(*args, **kwargs):
    """Only retry idempotent operations; claiming a code is deliberately once-only."""
    for attempt in range(5):
        try:
            return post(*args, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 4:
                raise
            time.sleep(2**attempt)


def check_info(info, expected_id):
    if (
        not info
        or info.get("_type", "video") != "video"
        or info.get("id") != expected_id
    ):
        raise ValueError("The link must identify a single YouTube video.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise ValueError("Live and upcoming streams are not supported.")
    if info.get("license") != CC_LICENSE:
        raise ValueError(
            "YouTube does not identify this video as Creative Commons Attribution licensed."
        )


def download(job, directory):
    if not re.fullmatch(
        r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", job["url"]
    ):
        raise ValueError("The transfer must identify a single YouTube video.")
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "Install ffmpeg and add it to PATH, then start again in video2commons."
        )
    expected_id = parse_qs(urlsplit(job["url"]).query)["v"][0]
    video = job["video"]
    audio = job["audio"]
    if video and audio:
        selector = "bestvideo+bestaudio/best"
    elif video:
        selector = "bestvideo/best"
    else:
        selector = "bestaudio/best"

    def match_filter(info, *, incomplete=False):
        if not incomplete:
            check_info(info, expected_id)

    def size_limit(progress):
        if progress.get("downloaded_bytes", 0) > job["max_size"]:
            raise RuntimeError(
                "The video exceeds the local transfer size limit (5 GiB)."
            )

    opts = {
        "format": selector,
        "outtmpl": str(Path(directory) / "media.%(ext)s"),
        "noplaylist": True,
        "cachedir": False,
        "max_filesize": job["max_size"],
        "match_filter": match_filter,
        "progress_hooks": [size_limit],
        "merge_output_format": "mkv",
        "overwrites": False,
        "socket_timeout": 30,
        # Let yt-dlp use an installed supported JS runtime for YouTube challenges.
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with yt_dlp.YoutubeDL(opts) as dl:
        # License validation happens before downloading any media.
        info = dl.extract_info(job["url"], download=False)
        check_info(info, expected_id)
        dl.process_ie_result(info, download=True)
    files = [
        p
        for p in Path(directory).glob("media.*")
        if p.suffix[1:]
        in {
            "webm",
            "mkv",
            "mp4",
            "m4a",
            "ogg",
            "opus",
        }
    ]
    if len(files) != 1:
        raise RuntimeError(
            "Could not find the finished media file. Update yt-dlp and try again."
        )
    path = files[0]
    if not 0 < path.stat().st_size <= job["max_size"]:
        raise RuntimeError("The downloaded file is empty or exceeds 5 GiB.")
    return path, {key: info.get(key) for key in METADATA_FIELDS}


def transfer(http, server, job, path, metadata):
    endpoint = job["id"]
    token = job["token"]
    size = path.stat().st_size
    data = retry_post(
        http,
        server,
        endpoint + "/begin",
        token,
        json={
            "size": size,
            "extension": path.suffix[1:],
            "metadata": metadata,
        },
    )
    offset = data["offset"]
    chunk_size = min(job["chunk_size"], 4_000_000)
    with path.open("rb") as media:
        while offset < size:
            media.seek(offset)
            chunk = media.read(chunk_size)
            result = retry_post(
                http,
                server,
                endpoint + "/chunk",
                token,
                data=chunk,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}",
                },
            )
            next_offset = result.get("offset")
            if type(next_offset) is not int or not offset < next_offset <= size:
                raise RuntimeError("Invalid upload offset returned by video2commons.")
            offset = next_offset
            print(
                f"\rSending to video2commons: {100 * offset // size}%",
                end="",
                flush=True,
            )
    retry_post(http, server, endpoint + "/complete", token)
    print(
        "\nReady. Return to video2commons to review the description and confirm the Commons upload."
    )


def main():
    print("video2commons local agent — one YouTube video per pairing")
    print("This downloads media on this computer and sends it to video2commons.")
    job = None
    try:
        server, code = parse_pairing(
            input("Paste the pairing code from video2commons: ")
        )
        with requests.Session() as http:
            http.headers["User-Agent"] = "video2commons-local-agent/1.0"
            job = post(http, server, "claim", code)
            print("YouTube video:", job["url"])
            if (
                input("Download this video and send it to video2commons? [y/N] ")
                .strip()
                .lower()
                != "y"
            ):
                post(
                    http,
                    server,
                    job["id"] + "/error",
                    job["token"],
                    json={"error": "Cancelled in the local agent."},
                )
                return 1
            try:
                with tempfile.TemporaryDirectory(prefix="video2commons-") as directory:
                    path, metadata = download(job, directory)
                    transfer(http, server, job, path, metadata)
            except (Exception, KeyboardInterrupt) as exc:
                message = str(exc) or "Cancelled in the local agent."
                try:
                    post(
                        http,
                        server,
                        job["id"] + "/error",
                        job["token"],
                        json={"error": message[:2000]},
                    )
                except (requests.RequestException, RuntimeError, ValueError):
                    print(
                        "Could not report the error. Cancel the transfer in the browser.",
                        file=sys.stderr,
                    )
                raise
        return 0
    except (
        requests.RequestException,
        ValueError,
        RuntimeError,
        OSError,
        yt_dlp.utils.DownloadError,
        KeyboardInterrupt,
    ) as exc:
        print("\nLocal transfer failed:", str(exc) or "Cancelled.", file=sys.stderr)
        print(
            "Update yt-dlp and check your network. YouTube can also block local downloads.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
