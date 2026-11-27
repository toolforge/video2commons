"""Tests for the "Import subtitles" checkbox of a task in the worker.

The frontend sends the checkbox as a form value, so the worker gets the string
"true" or "false": an unchecked box must not import any subtitles.
"""

import collections
import os
from types import SimpleNamespace

import pytest
import pywikibot

from video2commons.backend import worker

TASK_ID = "00000000-0000-4000-8000-000000000000"
FILE_URL = "https://commons.wikimedia.org/wiki/File:Example_video.webm"


class FakeRedis:
    """The few Redis commands that the worker runs itself."""

    def exists(self, key):
        return False

    def setex(self, key, ttl, value):
        pass


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Replace everything the worker talks to with fakes."""
    task_run = SimpleNamespace(
        # Languages of the subtitles of the source, which yt-dlp downloads
        # only when it is asked to.
        available=["en"],
        # The subtitles argument of the download.
        downloads=[],
        # Languages of the subtitles uploaded as TimedText pages.
        uploads=[],
        # Languages given to the subtitle categories.
        categories=[],
        # Uses of the subtitles of the container, when yt-dlp found none.
        container=[],
    )

    monkeypatch.setattr(worker, "redisconnection", FakeRedis())
    monkeypatch.setattr(worker, "OUTPUT_DIR", f"{tmp_path}/output/")
    monkeypatch.setattr(
        worker.os,
        "statvfs",
        lambda path: SimpleNamespace(f_frsize=1, f_bavail=100 << 30),
        raising=False,
    )
    monkeypatch.setattr(worker, "update_task_stats", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker.EncodingTask, "update_state", lambda self, **kwargs: None
    )
    monkeypatch.setattr(worker.EncodingTask, "is_aborted", lambda self, **kwargs: False)
    monkeypatch.setattr(worker, "publish_notification", lambda *args: None)
    monkeypatch.setattr(worker, "get_task_status", lambda *args: {})

    # The stages of a task.
    def download(conn, url, ie_key, key, subtitles, outputdir, status, error):
        task_run.downloads.append(subtitles)
        target = os.path.join(outputdir, "source.mkv")
        open(target, "wb").close()
        found = {}
        if subtitles:
            for lang in task_run.available:
                found[lang] = os.path.join(outputdir, f"source.{lang}.srt")
        return {"target": target, "subtitles": found}

    def encode(source, key, status, error, concurrency):
        target = source + ".av1.webm"
        open(target, "wb").close()
        return target

    def upload(file, filename, url, filedesc, username, status, error):
        return filename, FILE_URL

    monkeypatch.setattr(worker.download, "download", download)
    monkeypatch.setattr(worker.encode, "encode", encode)
    monkeypatch.setattr(worker.upload, "upload", upload)

    # What is done with the subtitles.
    def get_subtitle_categories(source, langcodes):
        task_run.categories.extend(sorted(langcodes))
        return []

    def upload_subtitles(subtitles, filename, username, status, error):
        task_run.uploads.append(sorted(subtitles))

    def get_container_subtitle_languages(source):
        task_run.container.append("languages")
        return set()

    def upload_container_subtitles(**kwargs):
        task_run.container.append("upload")

    monkeypatch.setattr(worker.categories, "get_inferable_categories", lambda f: [])
    monkeypatch.setattr(
        worker.categories, "get_subtitle_categories", get_subtitle_categories
    )
    monkeypatch.setattr(
        worker.categories, "append_categories", lambda desc, categories: desc
    )
    monkeypatch.setattr(
        worker.subtitleuploader, "get_subtitle_languages", lambda subs: set(subs)
    )
    monkeypatch.setattr(worker.subtitleuploader, "upload_subtitles", upload_subtitles)
    monkeypatch.setattr(
        worker.subtitleuploader,
        "get_container_subtitle_languages",
        get_container_subtitle_languages,
    )
    monkeypatch.setattr(
        worker.subtitleuploader,
        "upload_container_subtitles",
        upload_container_subtitles,
    )

    # Pywikibot, without any connection to Commons.
    class Site:
        def __init__(self, code, fam, user):
            pass

        def login(self):
            pass

    monkeypatch.setattr(pywikibot, "Site", Site)
    monkeypatch.setattr(pywikibot, "stopme", lambda: None)
    monkeypatch.setattr(pywikibot, "_sites", {})
    monkeypatch.setattr(pywikibot.config, "authenticate", {})
    monkeypatch.setattr(pywikibot.config, "usernames", collections.defaultdict(dict))

    worker.main.push_request(id=TASK_ID, hostname="celery@encoding01")
    yield task_run
    worker.main.pop_request()


def start_task(subtitles):
    """Run the task in the current process, as a worker does."""
    return worker.main.run(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "Youtube",
        subtitles,
        "Example video",
        "== Summary ==",
        "bestvideo+bestaudio/best",
        "av1.webm",
        "Example",
        ("access-token", "access-secret"),
    )


@pytest.mark.parametrize("subtitles", ["false", "False", False])
def test_unchecked_box_imports_no_subtitles(run, subtitles):
    assert start_task(subtitles)["type"] == "done"

    # yt-dlp must not even download them.
    assert run.downloads == [False]
    assert run.uploads == []
    assert run.categories == []
    assert run.container == []


@pytest.mark.parametrize("subtitles", ["true", "True", True])
def test_checked_box_imports_the_subtitles(run, subtitles):
    assert start_task(subtitles)["type"] == "done"

    assert run.downloads == [True]
    assert run.uploads == [["en"]]
    assert run.categories == ["en"]
    assert run.container == []


def test_checked_box_falls_back_to_the_container(run):
    # yt-dlp found no subtitles, as for a file uploaded from a computer.
    run.available = []

    assert start_task("true")["type"] == "done"

    assert run.uploads == []
    assert run.container == ["languages", "upload"]
