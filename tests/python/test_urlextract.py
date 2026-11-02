"""Tests for video2commons.frontend.urlextract."""

import importlib
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

import video2commons

# Modules imported by urlextract that need a configuration, a network or
# dependencies that aren't installed for the tests.
STUBBED_MODULES = [
    "emoji",
    "guess_language",
    "pywikibot",
    "yt_dlp",
    "video2commons.backend",
    "video2commons.backend.encode",
    "video2commons.backend.encode.transcode",
    "video2commons.frontend.shared",
    "video2commons.frontend.wcqs",
    "video2commons.shared.ratelimiting",
    "video2commons.shared.yt_dlp",
]


@pytest.fixture
def urlextract(monkeypatch):
    """Import urlextract with its heavy dependencies stubbed out."""
    for name in STUBBED_MODULES:
        monkeypatch.setitem(sys.modules, name, mock.MagicMock())

    # Importing the frontend package would start the whole Flask app.
    frontend = types.ModuleType("video2commons.frontend")
    frontend.__path__ = [str(Path(video2commons.__path__[0]) / "frontend")]
    monkeypatch.setitem(sys.modules, "video2commons.frontend", frontend)
    monkeypatch.delitem(sys.modules, "video2commons.frontend.urlextract", raising=False)

    module = importlib.import_module("video2commons.frontend.urlextract")
    yield module
    sys.modules.pop("video2commons.frontend.urlextract", None)


def mock_api(urlextract, parse, spamblacklist=None):
    """Mock the MediaWiki API responses used to validate a description."""
    responses = {"parse": parse, "spamblacklist": spamblacklist}

    def simple_request(action, **kwargs):
        request = mock.MagicMock()
        request.submit.return_value = responses[action]
        return request

    urlextract.SITE.simple_request.side_effect = simple_request


def test_do_validate_filedesc_normalizes_categories(urlextract):
    mock_api(urlextract, {"parse": {"externallinks": []}})

    filedesc = urlextract.do_validate_filedesc(
        "Description\n[[ category: a ]] [[ category: b_c]]"
    )

    assert filedesc == "Description\n[[Category:a]]\n[[Category:b c]]"
    urlextract.SITE.simple_request.assert_called_once_with(
        action="parse", text=filedesc, prop="externallinks"
    )


def test_do_validate_filedesc_spam_blacklist(urlextract):
    mock_api(
        urlextract,
        {"parse": {"externallinks": ["https://spam.example"]}},
        {"spamblacklist": {"result": "blacklisted", "matches": ["spam.example"]}},
    )

    with pytest.raises(AssertionError, match="spam blacklist! Matches: spam.example"):
        urlextract.do_validate_filedesc("[[category:a]] https://spam.example")
