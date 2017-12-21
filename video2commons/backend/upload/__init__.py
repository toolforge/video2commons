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
# along with self program.  If not, see <http://www.gnu.org/licenses/>
#

"""
Upload a file.

Wrapper around pywikibot when the file can be uploaded automatically.
If not, NeedServerSideUpload with url of file is thrown
"""

from __future__ import absolute_import

import os
import shutil
import pywikibot
import hashlib

from video2commons.config import http_host
from video2commons.exceptions import NeedServerSideUpload


def upload(task):
    """Upload a file from filename to wikifilename."""
    filename = task.results['encode']
    wikifilename = task.args.filename + u'.' + filename.split('.')[-1]

    size = os.path.getsize(filename)

    if size < 10**9:
        return upload_pwb(task, filename, wikifilename, size)
    elif size < (4 << 30):
        try:
            return upload_pwb(task, filename, wikifilename, size)
        except pywikibot.data.api.APIError as e:
            if 'stash' in e.code or e.code == 'backend-fail-internal':
                upload_ss(task, filename, wikifilename)
            else:
                raise
    else:
        task.error(
            'Sorry, but files larger than 4GB can not be uploaded even ' +
            'with server-side uploading. This task may need manual ' +
            ' intervention.'
        )


def upload_pwb(task, filename, wikifilename, size):
    """Upload with pywikibot."""
    # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
    site = pywikibot.Site('commons', 'commons', user=task.args.username)
    page = pywikibot.FilePage(site, wikifilename)

    if page.exists():
        task.error('File already exists. Please choose another name.')

    comment = u'Imported media from ' + task.args.url
    chunked = (16 * (1 << 20)) if size >= 100000000 else 0

    with task.status._pause():
        task.status.text = 'Uploading with pywikibot...'
        task.status.percent = -1
    try:
        if not site.upload(
            page, source_filename=filename, comment=comment,
            text=task.args.filedesc, chunk_size=chunked, async=bool(chunked)
            # , ignore_warnings=['exists-normalized']
        ):
            task.error('Upload failed!')
    except pywikibot.data.api.APIError:
        # recheck
        site.loadpageinfo(page)
        if not page.exists():
            raise

    with task.status._pause():
        task.status.text = 'Upload success!'
        task.status.percent = 100
    return page.title(withNamespace=False), page.full_url()


def upload_ss(task, filename, wikifilename):
    """Prepare for server-side upload."""
    with task.status._pause():
        task.status.text = 'Preparing for server-side upload...'
        task.status.percent = -1

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
    shutil.move(filename, newfilename)

    with open(newfilename + '.txt', 'w') as filedescfile:
        filedesc = task.args.filedesc.replace(
            '[[Category:Uploaded with video2commons]]',
            '[[Category:Uploaded with video2commons/Server-side uploads]]'
        )
        filedescfile.write(filedesc.encode('utf-8'))

    fileurl = 'https://' + http_host + '/' + wikifilename

    raise NeedServerSideUpload(fileurl, md5.hexdigest())
