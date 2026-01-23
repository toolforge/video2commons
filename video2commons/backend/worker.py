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

"""video2commons backend worker."""



import os
import sys
import shutil
import re

import celery
from celery.contrib.abortable import AbortableTask
from celery.exceptions import Ignore
from redis import Redis
import pywikibot

from video2commons.exceptions import TaskError, TaskAbort, NeedServerSideUpload
from video2commons.backend import download
from video2commons.backend import encode
from video2commons.backend import upload
from video2commons.backend import subtitles as subtitleuploader
from video2commons.config import (
    redis_pw, redis_host, consumer_key, consumer_secret, http_host
)
from video2commons.shared.stats import update_task_stats

redisurl = 'redis://:' + redis_pw + '@' + redis_host + ':6379/'
app = celery.Celery(
    'v2cbackend',
    backend=redisurl + '1',
    broker=redisurl + '2'
)
app.conf.result_expires = 30 * 24 * 3600  # 1 month

app.conf.accept_content = ['json']
app.conf.worker_prefetch_multiplier = 1

redisconnection = Redis(host=redis_host, db=3, password=redis_pw)


class Stats:
    """Storage for task status."""

    text = ''
    percent = 0


def get_worker_concurrency():
    """Parse concurrency value from CELERYD_OPTS environment variable."""
    celeryd_opts = os.environ.get('CELERYD_OPTS', '')

    match = re.search(r'--concurrency[=\s]+(\d+)', celeryd_opts)
    if match:
        return int(match.group(1))


@app.task(bind=True, track_started=False, base=AbortableTask)
def main(
    self, url, ie_key, subtitles, filename, filedesc,
    downloadkey, convertkey, username, oauth
):
    """Main worker code."""
    # Get a lock to prevent double-running with same task ID
    lockkey = 'tasklock:' + self.request.id
    if redisconnection.exists(lockkey):
        raise Ignore

    # Immediately increment the processing count in stats since the cron job
    # may take a while to update it (it takes a while to poll).
    try:
        update_task_stats(redisconnection, self.request.id, remove=False)
    except Exception:
        pass  # We don't want to fail the task if we can't update stats.

    # Check for 10G of disk space, refuse to run if it is unavailable
    st = os.statvfs('/srv')
    if st.f_frsize * st.f_bavail < 10 << 30:
        self.retry(max_retries=20, countdown=5*60)
        assert False  # should never reach here

    redisconnection.setex(lockkey, 7 * 24 * 3600, self.request.hostname)

    # Generate temporary directory for task
    for i in range(10):  # 10 tries
        id = os.urandom(8).hex()
        outputdir = '/srv/v2c/output/' + id
        if not os.path.isdir(outputdir):
            os.makedirs(outputdir)
            break
    else:
        raise TaskError("Too many retries to generate a task id")

    s = Stats()

    def statuscallback(text, percent):
        if self.is_aborted():
            raise TaskAbort
        if text is not None:
            s.text = text
        if percent is not None:
            s.percent = percent
        print('%d: %s' % (s.percent, s.text))

        self.update_state(
            state='PROGRESS',
            meta={'text': s.text, 'percent': s.percent}
        )

    def errorcallback(text):
        raise TaskError(text)

    try:
        statuscallback('Downloading...', -1)
        d = download.download(
            url, ie_key, downloadkey, subtitles,
            outputdir, statuscallback, errorcallback
        )
        if not d:
            errorcallback('Download failed!')
        file = d['target']
        if not file:
            errorcallback('Download failed!')

        source = file
        subtitles_requested = subtitles
        subtitles = subtitles and d['subtitles']

        statuscallback('Converting...', -1)
        concurrency = get_worker_concurrency()
        file = encode.encode(
            file, convertkey, statuscallback, errorcallback, concurrency
        )
        if not file:
            errorcallback('Convert failed!')
        ext = file.split('.')[-1]

        statuscallback('Configuring Pywikibot...', -1)
        pywikibot.config.authenticate['commons.wikimedia.org'] = \
            (consumer_key, consumer_secret) + tuple(oauth)
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
            try:
                subtitleuploader.upload_subtitles(
                    subtitles, filename, username,
                    statuscallback, errorcallback
                )
            except TaskAbort:
                raise
            except Exception as e:
                statuscallback(type(e).__name__ + ": " + str(e), None)
                print(e)
        elif subtitles_requested:
            # Fallback to extracting subtitles from the container if yt-dlp was
            # unable to find subtitles. This happens with manual mkv uploads
            # that contain embedded subtitles.
            try:
                subtitleuploader.upload_container_subtitles(
                    filepath=source,
                    filename=filename,
                    outputdir=outputdir,
                    username=username,
                    statuscallback=statuscallback
                )
            except TaskAbort:
                raise
            except Exception as e:
                statuscallback(type(e).__name__ + ": " + str(e), None)
                print(e)

    except NeedServerSideUpload as e:
        # json serializer cannot properly serialize an exception
        # without losing data, so we change the exception into a dict.
        return {'type': 'ssu', 'hashsum': e.hashsum, 'url': e.url}
    except pywikibot.exceptions.Error:
        exc_info = sys.exc_info()
        raise TaskError(
            (
                'pywikibot.Error: %s: %s' % (
                    exc_info[0].__name__, exc_info[1]
                )
            ).encode('utf-8')).with_traceback(exc_info[2])
    else:
        statuscallback('Done!', 100)
        return {'type': 'done', 'filename': filename, 'url': wikifileurl}
    finally:
        statuscallback('Cleaning up...', -1)
        pywikibot.stopme()
        pywikibot.config.authenticate.clear()
        pywikibot.config.usernames['commons'].clear()
        pywikibot._sites.clear()

        shutil.rmtree(outputdir)

        try:
            update_task_stats(redisconnection, self.request.id, remove=True)
        except Exception:
            pass  # We don't want to fail the task if we can't update stats.
