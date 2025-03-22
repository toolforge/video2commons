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
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#

"""Wrapper around youtube-dl."""



import os
from urllib.parse import urlparse

from celery.utils.log import get_logger
import yt_dlp
from yt_dlp.utils import std_headers, DownloadError

from video2commons.config import youtube_user, youtube_pass
from video2commons.exceptions import TaskError


def download(
    url, ie_key, formats, subtitles, outputdir,
    statuscallback=None, errorcallback=None
):
    """Download a video from url to outputdir."""

    if url.startswith('uploads:'):
        # FIXME; this should be a configuration variable
        url = url.replace('uploads:', 'https://video2commons.toolforge.org/'
                                      'static/uploads/', 1)
        ie_key = None

    url_blacklisted(url)

    outputdir = os.path.abspath(outputdir)
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)
    outtmpl = outputdir + '/dl.%(ext)s'

    params = {
        'format': formats,
        'outtmpl': outtmpl,
        'writedescription': True,
        'writeinfojson': True,
        'writesubtitles': subtitles,
        'writeautomaticsub': False,
        'subtitleslangs': ['all', '-live_chat'],
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
        'logger': get_logger('celery.task.v2c.main.yt_dlp')
    }

    old_ua = std_headers['User-Agent']
    if ie_key == 'Youtube':
        # HACK: Get equirectangular for 360° videos (ytdl-org/youtube-dl#15267)
        std_headers['User-Agent'] = ''
        params.update({
            'username': youtube_user,
            'password': youtube_pass
            })

    last_percentage = [Ellipsis]

    def progresshook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            percentage = int(100.0 * d['downloaded_bytes'] / total)\
                if total else None
            if percentage != last_percentage[0]:
                last_percentage[0] = percentage
                statuscallback(
                    'Downloading to ' + (d['tmpfilename'] or d['filename']),
                    percentage
                )
        elif d['status'] == 'finished':
            statuscallback('Postprocessing...', -1)
        elif d['status'] == 'error':
            errorcallback('Error raised by YoutubeDL')

    statuscallback('Creating YoutubeDL instance', -1)

    try:
        # Not using provided ie_key because of the existance of extractors that
        # targets another extractor, such as TwitterIE.
        with yt_dlp.YoutubeDL(params) as dl:
            dl.add_progress_hook(progresshook)
            statuscallback('Preprocessing...', -1)
            info = dl.extract_info(url, download=True, ie_key=None)
    except DownloadError:
        params['cachedir'] = False
        statuscallback('Download failed.'
                       ' creating YoutubeDL instance without local cache', -1)
        with yt_dlp.YoutubeDL(params) as dl:
            dl.add_progress_hook(progresshook)
            info = dl.extract_info(url, download=True, ie_key=None)

    finally:
        std_headers['User-Agent'] = old_ua

    if info.get('webpage_url'):
        url_blacklisted(info['webpage_url'])

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


def url_blacklisted(url):
    """Define download url blacklist."""
    parseresult = urlparse(url)
    if parseresult.scheme in ['http', 'https']:
        if parseresult.netloc.endswith('.googlevideo.com'):
            raise TaskError('Your downloading URL has been blacklisted.')
