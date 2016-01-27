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
import celery
import shutil
import download, encode, upload
import subtitles as subtitleuploader
from config import redis_pw

# TODO
redisurl = 'redis://:'+redis_pw+'@encoding01.video.eqiad.wmflabs:6379/'
app = celery.Celery('v2cbackend', backend=redisurl+'1', broker=redisurl+'2')
app.conf.CELERY_TASK_RESULT_EXPIRES = 30 * 24 * 3600 # 1 month

class stats:
    text = ''
    percent = 0

class TaskError(Exception):
    # So no one should handle it
    def __init__(self, desc):
        super(TaskError, self).__init__(desc)
        

@app.task(bind=True, track_started=True)
def main(self, url, ie_key, subtitles, filename, filedesc, convertkey, username, oauth):
    outputdir = generate_dir()
    s = stats()
    def statuscallback(text, percent):
        if text is not None: s.text = text
        if percent is not None: s.percent = percent
        print '%d: %s' % (percent, text)
        self.update_state(state='PROGRESS',
            meta={'text': s.text, 'percent': s.percent})

    def errorcallback(text):
        raise TaskError(text)

    statuscallback('Downloading...', -1)
    d = download.download(url, ie_key, 'bestvideo+bestaudio/best', subtitles, outputdir, statuscallback, errorcallback)
    if not d: errorcallback('Download failed!')
    file = d['target']
    if not file: errorcallback('Download failed!')
    subtitles = subtitles and d['subtitles']

    statuscallback('Converting...', -1)
    file = encode.encode(file, convertkey, statuscallback, errorcallback)
    if not file: errorcallback('Convert failed!')
    ext = file.split('.')[-1]

    statuscallback('Configuring Pywikibot...', -1)
    import pywikibot
    pywikibot.config.authenticate['commons.wikimedia.org'] = oauth
    pywikibot.config.usernames['commons']['commons'] = username
    pywikibot.Site('commons', 'commons', user=username).login()

    statuscallback('Uploading...', -1)
    fileurl = 'http://v2c.wmflabs.org/' + '/'.join(file.split('/')[3:])
    filename += '.' + ext
    filename, wikifileurl = upload.upload(file, filename, url, fileurl, filedesc, username, statuscallback, errorcallback)
    if not wikifileurl: errorcallback('Upload failed!')

    if subtitles:
        statuscallback('Uploading subtitles...', -1)
        try:
            subtitleuploader.subtitles(subtitles, filename, username, statuscallback, errorcallback)
        except:
            pass

    statuscallback('Cleaning up...', -1)
    pywikibot.config.authenticate.clear()
    pywikibot.config.usernames['commons'].clear()
    pywikibot._sites.clear()

    shutil.rmtree(outputdir)

    statuscallback('Done!', 100)

    return filename, wikifileurl

def generate_dir():
    for i in range(10): # 10 tries
        id = os.urandom(8).encode('hex')
        outputdir = '/srv/v2coutput/' + id
        if not os.path.isdir(outputdir):
            os.mkdir(outputdir)
            return outputdir
    else:
        raise TaskError("Too many retries to generate a task id")