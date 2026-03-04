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

"""Utility functions related to errors."""

import re


# KNOWN_ERRORS is a mapping of known and common errors that occur while using
# video2commons. The goal of this mapping is to make these common errors more
# human-readable.
#
# This is a breakdown of what each of the properties mean:
#
# - pattern: A regular expression that matches the original error message.
# - i18n_key: The key of the i18n message to use for this error.
# - urls: A list of URLs that the translated error message contains.
# - reportable: Whether the error is reportable from the modal or not.
KNOWN_ERRORS = [
    {
        # YouTube sometimes returns empty files when rate limiting.
        "pattern": r"DownloadError: ERROR: The downloaded file is empty",
        "i18n_key": "generic-ratelimit-error",
    },
    {
        # In the case of YouTube this is a rate limit error, but it might mean
        # otherwise for other services. Since YouTube is used most heavily we
        # assume it's probably a rate limiting error.
        "pattern": r"DownloadError: ERROR: unable to download video data: HTTP Error 403: Forbidden",
        "i18n_key": "generic-ratelimit-error",
    },
    {
        "pattern": r"DownloadError: ERROR: \[youtube\] [a-zA-Z0-9_-]{11}: Video unavailable\. This content isn’t available, try again later\. Your account has been rate-limited by YouTube for up to an hour\.",
        "i18n_key": "youtube-ratelimit-error",
    },
    {
        "pattern": r"DownloadError: ERROR: \[youtube\] [a-zA-Z0-9_-]{11}: Requested format is not available\.",
        "i18n_key": "youtube-ratelimit-error",
    },
    {
        "pattern": r"DownloadError: ERROR: \[youtube\] [a-zA-Z0-9_-]{11}: Sign in to confirm you’re not a bot\.",
        "i18n_key": "youtube-bot-error",
    },
    {
        "pattern": r"DownloadError: ERROR: \[youtube\] [a-zA-Z0-9_-]{11}: Private video",
        "i18n_key": "youtube-private-error",
    },
    {
        # This happens if the titleblacklist regex finds a match in the file's
        # title. The error message returned by pywikibot is confusing and
        # doesn't give the user any useful information to act on.
        "pattern": r"pywikibot\.Error: APIError: titleblacklist-forbidden",
        "i18n_key": "title-forbidden-error",
        "urls": ["https://commons.wikimedia.org/wiki/Commons:File_naming"],
    },
    {
        "pattern": r"DownloadError: ERROR: \[generic\] Unable to download webpage: HTTP Error 404",
        "i18n_key": "video-not-found-error",
    },
    {
        # The AV1 encoder will return this error if invalid parameters or a
        # stream format are passed to it. This is probably something we should
        # fix if this happens.
        "pattern": r"Exitcode: 234$",
        "i18n_key": "unsupported-format-error",
        "reportable": True,
    },
    {
        "pattern": r"Exitcode: 137$",
        "i18n_key": "out-of-memory-error",
        "reportable": True,
    },
    {
        # Segfaults are likely to be caused by OOM issues with the AV1 encoder,
        # but it's not safe to assume that. Encodes can alternate between
        # segfaulting and getting killed before it has a chance to segfault.
        "pattern": r"Exitcode: 139$",
        "i18n_key": "segfault-error",
        "reportable": True,
    },
]


def normalize_error(message: str) -> dict | None:
    """Normalize an error message to a human-readable i18n key."""
    for entry in KNOWN_ERRORS:
        if re.search(entry["pattern"], message):
            return entry.copy()

    return None
