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

"""video2commons backend worker."""

import os
import sys
import celery
from redis import Redis
import shutil
import pywikibot
import download
import encode
import upload
import subtitles as subtitleuploader
from config import (
    redis_pw, redis_host, consumer_key, consumer_secret, http_host
)

# TODO
redisurl = 'redis://:' + redis_pw + '@' + redis_host + ':6379/'
app = celery.Celery(
    'v2cbackend',
    backend=redisurl + '1',
    broker=redisurl + '2'
)
app.conf.CELERY_TASK_RESULT_EXPIRES = 30 * 24 * 3600  # 1 month

redisconnection = Redis(host=redis_host, db=3, password=redis_pw)


class Stats:
    """Storage for task status."""

    text = ''
    percent = 0


class TaskError(Exception):
    """A generic task error exception."""

    def __init__(self, desc):
        """Initialize."""
        super(TaskError, self).__init__(desc)


@app.task(bind=True, track_started=True)
def main(
    self, url, ie_key, subtitles, filename, filedesc,
    convertkey, username, oauth
):
    """Main worker code."""
    # Get a lock to prevent double-running with same task ID
    lockkey = 'tasklock:' + self.request.id
    if redisconnection.exists(lockkey):
        raise TaskError("Task has already been run")
    else:
        redisconnection.setex(lockkey, 'T', 7 * 24 * 3600)

    # Generate temporary directory for task
    for i in range(10):  # 10 tries
        id = os.urandom(8).encode('hex')
        outputdir = '/srv/v2c/output/' + id
        if not os.path.isdir(outputdir):
            os.mkdir(outputdir)
            break
    else:
        raise TaskError("Too many retries to generate a task id")

    s = Stats()

    def statuscallback(text, percent):
        if text is not None:
            s.text = text
        if percent is not None:
            s.percent = percent
        print '%d: %s' % (s.percent, s.text)

        self.update_state(
            state='PROGRESS',
            meta={'text': s.text, 'percent': s.percent}
        )

    def errorcallback(text):
        raise TaskError(text)

    try:
        statuscallback('Downloading...', -1)
        d = download.download(
            url, ie_key, 'bestvideo+bestaudio/best', subtitles,
            outputdir, statuscallback, errorcallback
        )
        if not d:
            errorcallback('Download failed!')
        file = d['target']
        if not file:
            errorcallback('Download failed!')
        subtitles = subtitles and d['subtitles']

        statuscallback('Converting...', -1)
        file = encode.encode(file, convertkey, statuscallback, errorcallback)
        if not file:
            errorcallback('Convert failed!')
        ext = file.split('.')[-1]

        statuscallback('Configuring Pywikibot...', -1)
        pywikibot.config.authenticate['commons.wikimedia.org'] = \
            (consumer_key, consumer_secret) + oauth
        pywikibot.config.usernames['commons']['commons'] = username
        pywikibot.Site('commons', 'commons', user=username).login()

        statuscallback('Uploading...', -1)
        filename += '.' + ext
        filename, wikifileurl = upload.upload(
            file, filename, url, http_host,
            filedesc, username, statuscallback, errorcallback
        )
        if not wikifileurl:
            errorcallback('Upload failed!')

        if subtitles:
            statuscallback('Uploading subtitles...', -1)
            try:
                subtitleuploader.subtitles(
                    subtitles, filename, username,
                    statuscallback, errorcallback
                )
            except Exception, e:
                statuscallback(type(e).__name__ + ": " + str(e), None)
                print e
                pass

    except pywikibot.Error:  # T124922 workaround
        exc_info = sys.exc_info()
        raise TaskError(
            (
                u'pywikibot.Error: %s: %s' % (
                    exc_info[0].__name__, exc_info[1]
                )
            ).encode('utf-8')), None, exc_info[2]
    else:
        statuscallback('Done!', 100)
        return filename, wikifileurl
    finally:
        statuscallback('Cleaning up...', -1)
        pywikibot.config.authenticate.clear()
        pywikibot.config.usernames['commons'].clear()
        pywikibot._sites.clear()

        shutil.rmtree(outputdir)
