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



import os
import shutil
import pywikibot
import hashlib

from video2commons.exceptions import NeedServerSideUpload


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
    elif size < (4 << 30):
        try:
            return upload_pwb(
                filename, wikifilename, sourceurl, filedesc, username,
                size, statuscallback, errorcallback
            )
        except pywikibot.data.api.APIError as e:
            if 'stash' in e.code or e.code == 'backend-fail-internal':
                upload_ss(
                    filename, wikifilename, http_host, filedesc,
                    statuscallback, errorcallback
                )
            else:
                raise
    else:
        errorcallback(
            'Sorry, but files larger than 4GB can not be uploaded even ' +
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

    statuscallback('Uploading...', -1)
    try:
        if not site.upload(page, **{
            'source_filename': filename,
            'comment': comment,
            'text': filedesc,
            'chunk_size': chunked,
            'async': bool(chunked),
            # 'ignore_warnings': ['exists-normalized'],
        }):
            errorcallback('Upload failed!')
    except pywikibot.data.api.APIError:
        # recheck
        site.loadpageinfo(page)
        if not page.exists():
            raise

    statuscallback('Upload success!', 100)
    return page.title(withNamespace=False), page.full_url()


def upload_ss(
    filename, wikifilename, http_host, filedesc,
    statuscallback, errorcallback
):
    """Prepare for server-side upload."""
    statuscallback('Preparing for server-side upload...', -1)

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
        filedesc = filedesc.replace(
            '[[Category:Uploaded with video2commons]]',
            '[[Category:Uploaded with video2commons/Server-side uploads]]'
        )
        filedescfile.write(filedesc.encode('utf-8'))

    fileurl = 'https://' + http_host + '/' + wikifilename

    raise NeedServerSideUpload(fileurl, md5.hexdigest())
