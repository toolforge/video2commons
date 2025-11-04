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
Upload a file.

Wrapper around pywikibot when the file can be uploaded automatically.
If not, NeedServerSideUpload with url of file is thrown
"""

import time
import os
import shutil
import pywikibot
import hashlib

from video2commons.exceptions import NeedServerSideUpload, TaskError

MAX_RETRIES = 5


def upload(
    filename, wikifilename, sourceurl, http_host, filedesc, username,
    statuscallback=None, errorcallback=None
):
    """Upload a file from filename to wikifilename."""
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)

    size = os.path.getsize(filename)

    if size < 1000000000:
        return upload_pwb(
            filename, wikifilename, sourceurl, filedesc, username,
            size, statuscallback, errorcallback
        )
    elif size < (5 << 30):
        try:
            return upload_pwb(
                filename, wikifilename, sourceurl, filedesc, username,
                size, statuscallback, errorcallback
            )
        except pywikibot.exceptions.APIError as e:
            if 'stash' in e.code or e.code == 'backend-fail-internal':
                upload_ss(
                    filename, wikifilename, http_host, filedesc,
                    statuscallback, errorcallback
                )
            else:
                raise
    else:
        errorcallback(
            'Sorry, but files larger than 5GB can not be uploaded even ' +
            'with server-side uploading. This task may need manual ' +
            ' intervention.'
        )


def upload_pwb(
    filename, wikifilename, sourceurl, filedesc, username,
    size, statuscallback, errorcallback
):
    """Upload with pywikibot."""
    # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
    site = pywikibot.Site('commons', 'commons', user=username)
    page = pywikibot.FilePage(site, wikifilename)

    if page.exists():
        errorcallback('File already exists. Please choose another name.')

    comment = 'Imported media from ' + sourceurl
    chunked = (16 * (1 << 20)) if size >= 100000000 else 0
    remaining_tries = MAX_RETRIES

    while True:
        if remaining_tries == MAX_RETRIES:
            statuscallback('Uploading...', -1)
        elif remaining_tries > 1:
            statuscallback(f'Retrying upload... ({remaining_tries} tries remaining)', -1)
        elif remaining_tries == 1:
            statuscallback(f'Retrying upload... ({remaining_tries} try remaining)', -1)

        if remaining_tries != MAX_RETRIES:
            exponential_backoff(remaining_tries)

        try:
            if not site.upload(
                page,
                source_filename=filename,
                comment=comment,
                text=filedesc,
                chunk_size=chunked,
                asynchronous=bool(chunked),
                ignore_warnings=['exists-normalized'],
            ):
                errorcallback('Upload failed!')

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

    statuscallback('Upload success!', 100)
    return page.title(with_ns=False), page.full_url()


def upload_ss(
    filename, wikifilename, http_host, filedesc,
    statuscallback, errorcallback
):
    """Prepare for server-side upload."""
    # Get hash
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            md5.update(data)

    # file name check
    wikifilename = wikifilename.replace('/', '-').replace(' ', '_')
    wikifilename = wikifilename.replace('\r\n', '_')
    wikifilename = wikifilename.replace('\r', '_').replace('\n', '_')

    newfilename = '/srv/v2c/ssu/' + wikifilename
    remaining_tries = MAX_RETRIES

    while True:
        try:
            if remaining_tries == MAX_RETRIES:
                statuscallback('Preparing for server-side upload...', -1)
            elif remaining_tries > 1:
                statuscallback(f'Retrying server-side upload preparation... ({remaining_tries} tries remaining)', -1)
            elif remaining_tries == 1:
                statuscallback(f'Retrying server-side upload preparation... ({remaining_tries} try remaining)', -1)

            if remaining_tries != MAX_RETRIES:
                exponential_backoff(remaining_tries)

            shutil.move(filename, newfilename)

            break  # The file was moved to the SSU share successfully.
        except BlockingIOError:
            # A BlockingIOError will be raised whenever the NFS share that SSU
            # files are kept on is overloaded.
            remaining_tries -= 1
            if remaining_tries == 0:
                # No more retries, raise the error.
                errorcallback('Upload failed: NFS share is likely overloaded')

    with open(newfilename + '.txt', 'w') as filedescfile:
        filedesc = filedesc.replace(
            '[[Category:Uploaded with video2commons]]',
            '[[Category:Uploaded with video2commons/Server-side uploads]]'
        )
        filedescfile.write(filedesc)

    fileurl = 'https://' + http_host + '/' + wikifilename

    raise NeedServerSideUpload(fileurl, md5.hexdigest())


def exponential_backoff(tries, max_tries=MAX_RETRIES, delay=20):
    """Exponential backoff doubling for every retry."""
    time.sleep(delay * (2 ** (max_tries - tries - 1)))
