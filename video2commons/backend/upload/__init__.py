#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General License for more details.
#
# You should have received a copy of the GNU General License
# along with self program.  If not, see <https://www.gnu.org/licenses/>
#

"""
Upload a file to Wikimedia Commons.

The upload function in this module acts as a wrapper around pywikibot's upload
method. It adds additional validation and retry handling for uploads.
"""

import os
import time

import pywikibot
from pywikibot.exceptions import (
    APIError,
    FatalServerError,
    ServerError,
    TimeoutError,
)

from video2commons.exceptions import TaskError

MAX_RETRIES = 5

# Wikimedia Commons has a maximum file size of 5 GiB for chunked uploads.
UPLOAD_LIMIT_BYTES = 5 * 1024 * 1024 * 1024

# Unchunked are limited to 100 MiB.
UNCHUNKED_LIMIT_BYTES = 100 * 1024 * 1024

# Limit chunk size to 16 MiB for chunked uploads exceeding 100 MiB.
CHUNK_SIZE = 16 * 1024 * 1024

IGNORED_WARNINGS = ["exists-normalized"]


def upload(
    filename,
    wikifilename,
    sourceurl,
    filedesc,
    username,
    statuscallback,
    errorcallback,
):
    """Upload files to Commons using pywikibot."""
    size = os.path.getsize(filename)

    if size >= UPLOAD_LIMIT_BYTES:
        errorcallback(
            "Sorry, but files larger than 5GiB cannot be uploaded. "
            "Manual uploads with SSU are no longer supported by Commons and "
            "cannot be used to circumvent this limit."
        )

    # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
    site = pywikibot.Site("commons", "commons", user=username)
    page = pywikibot.FilePage(site, wikifilename)

    if page.exists():
        errorcallback("File already exists. Please choose another name.")

    comment = "Imported media from " + sourceurl
    chunk_size = CHUNK_SIZE if size >= UNCHUNKED_LIMIT_BYTES else 0
    remaining_tries = MAX_RETRIES

    while True:
        if remaining_tries == MAX_RETRIES:
            statuscallback("Uploading...", -1)
        elif remaining_tries > 1:
            statuscallback(
                f"Retrying upload... ({remaining_tries} tries remaining)", -1
            )
        elif remaining_tries == 1:
            statuscallback(f"Retrying upload... ({remaining_tries} try remaining)", -1)

        if remaining_tries != MAX_RETRIES:
            exponential_backoff(remaining_tries)

        upload_warnings = []

        # Filter warnings using a custom callback instead of a list so we can
        # collect a list of UploadErrors corresponding to fatal warnings. The
        # list is bound as a default argument to be the one of this attempt.
        def ignore_warnings(warnings, upload_warnings=upload_warnings):
            upload_warnings.extend(
                w for w in warnings if w.code not in IGNORED_WARNINGS
            )
            return not upload_warnings

        try:
            site.upload(
                page,
                source_filename=filename,
                comment=comment,
                text=filedesc,
                chunk_size=chunk_size,
                asynchronous=bool(chunk_size),
                ignore_warnings=ignore_warnings,
            )

            # Setting 'ignore_warnings' makes site.upload() no longer raise
            # exceptions for any warnings not covered in the list, just a
            # falsey return value.
            #
            # Use a custom callback to collect fatal warnings and re-raise
            # those to workaround this so the full warning messages get shown
            # to the user.
            if len(upload_warnings) == 1:
                raise upload_warnings[0]
            elif len(upload_warnings) > 1:
                messages = ", ".join(str(w) for w in upload_warnings)
                raise TaskError(f"Upload failed due to multiple errors: {messages}")

            break  # The upload completed successfully.
        except (FatalServerError, TaskError):
            raise  # These will not be corrected by resending.
        except (ServerError, TimeoutError):
            # These errors are possibly transient, so retry them.
            remaining_tries -= 1
            if remaining_tries == 0:
                raise  # No more retries, raise the error.
        except APIError:
            # Recheck in case the error didn't prevent the upload.
            site.loadpageinfo(page)
            if page.exists():
                break  # The upload completed successfully.

            raise  # These errors are unlikely to be transient, so re-raise.
        except Exception:
            # Retry by default for any other errors.
            remaining_tries -= 1
            if remaining_tries == 0:
                raise  # No more retries, raise the error.

    statuscallback("Upload success!", 100)
    return page.title(with_ns=False), page.full_url()


def exponential_backoff(tries, max_tries=MAX_RETRIES, delay=20):
    """Exponential backoff doubling for every retry."""
    time.sleep(delay * (2 ** (max_tries - tries - 1)))
