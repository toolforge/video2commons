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
import pywikibot

def upload(filename, wikifilename, sourceurl, fileurl, filedesc, username,
        statuscallback = None, errorcallback = None):
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)

    size = os.path.getsize(filename)
    if size < 1000000000:
        # Upload
        # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
        site = pywikibot.Site('commons', 'commons', user=username)
        page = pywikibot.FilePage(site, wikifilename)
        comment = u'Imported media from ' + sourceurl
        chunked = (64 * (1 << 20)) if size >= 100000000 else 0

        statuscallback('Uploading...', -1)
        if site.upload(page, source_filename=filename, comment=comment, text=filedesc, chunk_size=chunked):
            statuscallback('Upload success!', 100)
            return page.title(withNamespace=False), page.full_url()
        else:
            errorcallback('Upload failed! You may want to upload the file manually from <a href="%s">%s</s>' % (fileurl, fileurl))

    else:
        # Source: videoconverter tool
        phabdesc = """Please upload this file to Wikimedia Commons using the filename "%s": %s
Please use the following description:
```
%s
```
Thank you!""" % (wikifilename, fileurl, 
            filedesc.replace('[[Category:Uploaded with video2commons]]', '[[Category:Uploaded with video2commons/Server-side uploads]]'))
        import urllib
        phaburl = 'https://phabricator.wikimedia.org/maniphest/task/create/?title=Please%20upload%20large%20file%20to%20Wikimedia%20Commons&projects=Wikimedia-Site-requests,commons&description=' + \
            urllib.quote(phabdesc)
        errorcallback('File too large to upload directly! You may want to <a href="%s">request a server-side upload</s>' % (phaburl))

