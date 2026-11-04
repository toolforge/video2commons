"""Tests for the explanation of the errors of a site that blocks video2commons.

When YouTube blocks the server, the user must learn that they can download
the video on their computer and upload it with its metadata, both in the add
task dialog (the URL can't be extracted) and in the tasks table (the encoder
can't download the video).
"""

import json

import pytest

from video2commons.frontend import api
from video2commons.shared import errors
from video2commons.shared.errors import LOCAL_DOWNLOAD_DOC_URL, normalize_error

YOUTUBE_URL = "https://www.youtube.com/watch?v=abcdefghijk"

# The errors of yt-dlp when a site blocks video2commons, as format_exception()
# shows them, with the i18n key of their explanation.
BLOCKED_ERRORS = {
    "An exception occurred: DownloadError: ERROR: [youtube] abcdefghijk: "
    "Sign in to confirm you’re not a bot. Use --cookies-from-browser or "
    "--cookies for the authentication.": "youtube-bot-error",
    "An exception occurred: DownloadError: ERROR: [youtube] abcdefghijk: "
    "Video unavailable. This content isn’t available, try again later. Your "
    "account has been rate-limited by YouTube for up to an hour.": (
        "youtube-ratelimit-error"
    ),
    "An exception occurred: DownloadError: ERROR: [youtube] abcdefghijk: "
    "Requested format is not available. Use --list-formats for a list of "
    "available formats": "youtube-ratelimit-error",
    "An exception occurred: DownloadError: ERROR: The downloaded file is empty": (
        "generic-ratelimit-error"
    ),
    "An exception occurred: DownloadError: ERROR: unable to download video "
    "data: HTTP Error 403: Forbidden": "generic-ratelimit-error",
}


@pytest.mark.parametrize(("message", "i18n_key"), BLOCKED_ERRORS.items())
def test_blocked_error_links_to_the_local_download(message, i18n_key):
    error = normalize_error(message)

    assert error["i18n_key"] == i18n_key
    assert error["urls"] == [LOCAL_DOWNLOAD_DOC_URL]


@pytest.mark.parametrize(
    "message",
    [
        (
            "An exception occurred: DownloadError: ERROR: [youtube] abcdefghijk: "
            "Private video. Sign in if you've been granted access to this video"
        ),
        (
            "An exception occurred: DownloadError: ERROR: [generic] Unable to "
            "download webpage: HTTP Error 404: Not Found"
        ),
    ],
)
def test_other_download_error_does_not_link_to_the_local_download(message):
    # Downloading the video on one's computer wouldn't help.
    assert "urls" not in normalize_error(message)


def test_only_blocked_errors_link_to_the_local_download():
    keys = {
        entry["i18n_key"]
        for entry in errors.KNOWN_ERRORS
        if LOCAL_DOWNLOAD_DOC_URL in entry.get("urls", [])
    }

    assert keys == set(BLOCKED_ERRORS.values())


def test_link_is_the_doc_of_the_repository():
    assert LOCAL_DOWNLOAD_DOC_URL == (
        "https://github.com/toolforge/video2commons/blob/master/"
        "docs/upload-info-json.md"
    )


def test_source_form_links_to_the_same_doc():
    with open("video2commons/frontend/static/templates/sourceForm.html") as f:
        assert f"{{% set localDownloadDocUrl = '{LOCAL_DOWNLOAD_DOC_URL}' %}}" in (
            f.read()
        )


@pytest.mark.parametrize("i18n_key", sorted(set(BLOCKED_ERRORS.values())))
def test_message_has_the_link(i18n_key):
    with open("video2commons/frontend/i18n/en.json", encoding="utf-8") as f:
        message = json.load(f)[i18n_key]

    assert message.count("{{#a}}") == 1
    assert message.count("{{/a}}") == 1
    assert "yt-dlp" in message


class ExtractionError(Exception):
    """An error of yt-dlp, whose type name is the one of format_exception()."""


ExtractionError.__name__ = "DownloadError"


def extract_url_failing_with(monkeypatch, message):
    def extract(url):
        raise ExtractionError(message)

    monkeypatch.setattr(api, "do_extract_url", extract)


@pytest.mark.parametrize(("message", "i18n_key"), BLOCKED_ERRORS.items())
def test_extracturl_explains_a_blocked_error(api_post, monkeypatch, message, i18n_key):
    error = message.removeprefix("An exception occurred: DownloadError: ")
    extract_url_failing_with(monkeypatch, error)

    data = api_post("extracturl", url=YOUTUBE_URL)

    assert data["step"] == "error"
    assert data["error"] == message
    assert data["i18n_key"] == i18n_key
    assert data["i18n_urls"] == [LOCAL_DOWNLOAD_DOC_URL]


def test_extracturl_explains_another_known_error(api_post, monkeypatch):
    extract_url_failing_with(monkeypatch, "ERROR: [youtube] abcdefghijk: Private video")

    data = api_post("extracturl", url=YOUTUBE_URL)

    assert data["i18n_key"] == "youtube-private-error"
    assert data["i18n_urls"] is None


def test_extracturl_keeps_an_unknown_error(api_post, monkeypatch):
    extract_url_failing_with(monkeypatch, "ERROR: something else")

    data = api_post("extracturl", url=YOUTUBE_URL)

    assert data["step"] == "error"
    assert data["error"] == (
        "An exception occurred: DownloadError: ERROR: something else"
    )
    assert data["i18n_key"] is None
    assert data["i18n_urls"] is None


def test_error_without_an_exception_is_unchanged(client):
    # error_json() with a message, e.g. a wrong CSRF token.
    response = client.post("/api/extracturl", data={"url": YOUTUBE_URL})

    assert response.get_json() == {
        "step": "error",
        "error": "Invalid CSRF token. Try reloading this page.",
        "traceback": None,
    }
