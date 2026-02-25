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

import time
import os
import pywikibot

from video2commons.exceptions import TaskError

MAX_RETRIES = 5

# Wikimedia Commons has a maximum file size of 5 GiB for chunked uploads.
UPLOAD_LIMIT_BYTES = 5 * 1024 * 1024 * 1024

# Unchunked are limited to 100 MiB.
UNCHUNKED_LIMIT_BYTES = 100 * 1024 * 1024

# Limit chunk size to 16 MiB for chunked uploads exceeding 100 MiB.
CHUNK_SIZE = 16 * 1024 * 1024


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

        try:
            if not site.upload(
                page,
                source_filename=filename,
                comment=comment,
                text=filedesc,
                chunk_size=chunk_size,
                asynchronous=bool(chunk_size),
                ignore_warnings=["exists-normalized"],
            ):
                errorcallback("Upload failed!")

            break  # The upload completed successfully.
        except TaskError:
            raise  # Don't retry errors caused by errorcallback.
        except pywikibot.exceptions.APIError:
            # Recheck in case the error didn't prevent the upload.
            site.loadpageinfo(page)
            if page.exists():
                break  # The upload completed successfully.

            remaining_tries -= 1
            if remaining_tries == 0:
                raise  # No more retries, raise the error.
        except Exception:
            remaining_tries -= 1
            if remaining_tries == 0:
                raise  # No more retries, raise the error.

    statuscallback("Upload success!", 100)
    return page.title(with_ns=False), page.full_url()


def exponential_backoff(tries, max_tries=MAX_RETRIES, delay=20):
    """Exponential backoff doubling for every retry."""
    time.sleep(delay * (2 ** (max_tries - tries - 1)))
