#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

"""Wrapper around youtube-dl."""

from __future__ import absolute_import

import os
from urlparse import urlparse

from celery.utils.log import get_logger
import youtube_dl


def download(task):
    """Download a video from url."""

    url, ie_key = task.args.url, task.args.ie_key
    if url.startswith('uploads:'):
        # FIXME; this should be a configuration variable
        url = url.replace('uploads:', 'https://tools.wmflabs.org/'
                                      'video2commons/static/uploads/', 1)
        ie_key = None

    url_blacklisted(url, task.error)
    outtmpl = u'./dl.%(ext)s'

    params = {
        'format': task.args.downloadkey,
        'outtmpl': outtmpl,
        'writedescription': True,
        'writeinfojson': True,
        'writesubtitles': task.args.subtitles,
        'writeautomaticsub': False,
        'allsubtitles': True,
        'subtitlesformat': 'srt/ass/vtt/best',
        'cachedir': '/tmp/',
        'noplaylist': True,  # not implemented in video2commons
        'postprocessors': [{
            'key': 'FFmpegSubtitlesConvertor',
            'format': 'srt',
        }],
        'max_filesize': 5 * (1 << 30),
        'retries': 10,
        'fragment_retries': 10,
        'prefer_ffmpeg': True,  # avconv do not have srt encoder
        'prefer_free_formats': True,
        'logger': get_logger('celery.task.v2c.main.youtube-dl')
    }

    def progresshook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            percentage = int(100.0 * d['downloaded_bytes'] / total)\
                if total else None
            with task.status._pause():
                task.status.text = (
                    'Downloading to ' + (d['tmpfilename'] or d['filename']))
                task.status.percent = percentage
        elif d['status'] == 'finished':
            with task.status._pause():
                task.status.text = 'Postprocessing...'
                task.status.percent = -1
        elif d['status'] == 'error':
            task.error('Error raised by YoutubeDL')

    with task.status._pause():
        task.status.text = 'Creating YoutubeDL instance'
        task.status.percent = -1

    dl = youtube_dl.YoutubeDL(params)
    dl.add_progress_hook(progresshook)

    task.status.text = 'Preprocessing...'
    info = dl.extract_info(url, download=True, ie_key=ie_key)

    if info.get('webpage_url'):
        url_blacklisted(info['webpage_url'], task.error)

    filename = outtmpl % {'ext': info['ext']}
    if not os.path.isfile(filename):
        # https://github.com/rg3/youtube-dl/issues/8349
        filename = outtmpl % {'ext': 'mkv'}
        assert os.path.isfile(filename), \
            'Failed to determine the path of the downloaded video. ' + \
            'Is the video too large?'

    ret = {
        'extractor': ie_key,
        'subtitles': {},
        'target': filename,
    }

    for key in info.get('subtitles', {}):
        # Postprocesed: converted to srt
        filename = outtmpl % {'ext': key + '.srt'}
        if os.path.isfile(filename):
            ret['subtitles'][key] = filename

    return ret


def url_blacklisted(url, cb):
    """Define download url blacklist."""
    parseresult = urlparse(url)
    if parseresult.scheme in ['http', 'https']:
        if parseresult.netloc.endswith('.googlevideo.com'):
            cb('Your downloading URL has been blacklisted.')
