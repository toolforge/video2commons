#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# Wrapper around pywikibot
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

import os
import shutil
import pywikibot

class NeedServerSideUpload(Exception):
    # So no one should handle it
    def __init__(self, url):
        super(NeedServerSideUpload, self).__init__(url)
        self.url = url

def upload(filename, wikifilename, sourceurl, http_host, filedesc, username,
        statuscallback = None, errorcallback = None):
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)

    size = os.path.getsize(filename)
    if size < 2000000000:
        # Upload
        # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
        site = pywikibot.Site('commons', 'commons', user=username)
        page = pywikibot.FilePage(site, wikifilename)

        if page.exists():
            errorcallback('File already exists. Please choose another name.')

        comment = u'Imported media from ' + sourceurl
        chunked = (64 * (1 << 20)) if size >= 100000000 else 0

        statuscallback('Uploading...', -1)
        if site.upload(page, source_filename=filename, comment=comment, text=filedesc, chunk_size=chunked, ignore_warnings=['exists-normalized']):
            statuscallback('Upload success!', 100)
            return page.title(withNamespace=False), page.full_url()
        else:
            errorcallback('Upload failed!')

    else:
        assert size < (1 << 32), 'Sorry, but files larger than 4GB can not be uploaded even with server-side uploading. This task may need manual intervention.'

        # file name check
        wikifilename = wikifilename.replace('/', '-').replace(' ', '_').replace('\r\n', '_').replace('\r', '_').replace('\n', '_')
        newfilename = '/srv/v2c/ssu/' + wikifilename
        shutil.move(filename, newfilename)

        with open(newfilename + '.txt', 'w') as filedescfile:
            filedesc = filedesc.replace('[[Category:Uploaded with video2commons]]', '[[Category:Uploaded with video2commons/Server-side uploads]]')
            filedescfile.write(filedesc.encode('utf-8'))

        fileurl = 'http://' + http_host + '/' + wikifilename

        raise NeedServerSideUpload(fileurl)