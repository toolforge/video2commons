"""Tests for the edit summary of an upload to Commons.

It says where the media was imported from, unless the tool that started the
task gives its own, e.g. a user script on Commons that names itself in it.
"""

import pytest

from video2commons.backend import upload

SOURCE = "uploads:00000000-0000-1000-8000-000000000000.mov"
SUMMARY = "Batch upload using [[User:Example/tool.js|tool]]"


class FakeSite:
    """A site of Pywikibot that keeps what it was asked to upload."""

    def __init__(self):
        self.uploads = []

    def upload(self, page, **kwargs):
        self.uploads.append(kwargs)
        return True


class FakePage:
    """A file page of Pywikibot that does not exist yet."""

    def __init__(self, site, title):
        self._title = title

    def exists(self):
        return False

    def title(self, with_ns=True):
        return self._title

    def full_url(self):
        return "https://commons.wikimedia.org/wiki/File:" + self._title


@pytest.fixture
def site(monkeypatch):
    site = FakeSite()
    monkeypatch.setattr(upload.pywikibot, "Site", lambda *args, **kwargs: site)
    monkeypatch.setattr(upload.pywikibot, "FilePage", FakePage)
    return site


def upload_video(tmp_path, **kwargs):
    video = tmp_path / "video.webm"
    video.write_bytes(b"\x1a\x45\xdf\xa3")

    def error(message):
        raise AssertionError(message)

    return upload.upload(
        str(video),
        "Example video.webm",
        SOURCE,
        "== Summary ==",
        "Example",
        lambda text, percent: None,
        error,
        **kwargs,
    )


def test_says_where_the_media_came_from(site, tmp_path):
    upload_video(tmp_path)

    assert site.uploads[0]["comment"] == "Imported media from " + SOURCE


def test_takes_the_summary_of_the_tool(site, tmp_path):
    assert upload_video(tmp_path, comment=SUMMARY) == (
        "Example video.webm",
        "https://commons.wikimedia.org/wiki/File:Example video.webm",
    )

    assert site.uploads[0]["comment"] == SUMMARY
