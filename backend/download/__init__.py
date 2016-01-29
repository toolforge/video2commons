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

import os
import youtube_dl # https://github.com/rg3/youtube-dl

class Downloader(object):
    def __init__(self, url, ie_key, formats, subtitles, outputdir,
            statuscallback = None, errorcallback = None):
        self.url = url
        self.ie_key = ie_key
        self.formats = formats
        self.subtitles = subtitles
        self.outputdir = os.path.abspath(outputdir)
        self.statuscallback = statuscallback or (lambda text, percent: None)
        self.errorcallback = errorcallback or (lambda text: None)
        self.outtmpl = self.outputdir + '/dl.%(ext)s'

    def run(self):
        params = {
            'format': self.formats,
            'outtmpl': self.outtmpl,
            'writedescription': True,
            'writeinfojson': True,
            'writesubtitles': self.subtitles,
            'writeautomaticsub': False,
            'allsubtitles': True,
            'subtitlesformat': 'srt/ass/vtt/best',
            'cachedir': '/tmp/',
            'noplaylist': True, # not implemented in video2commons
            'postprocessors': [{
                'key': 'FFmpegSubtitlesConvertor',
                'format': 'srt',
            }],
            'max_filesize': 5 * (1 << 30),
            'prefer_ffmpeg': True, # avconv do not have srt encoder
            'prefer_free_formats': True
        }

        self.statuscallback('Creating YoutubeDL instance', -1)
        self.dl = youtube_dl.YoutubeDL(params)
        self.dl.add_progress_hook(self.progresshook)

        self.statuscallback('Preprocessing...', -1)
        self.info = self.dl.extract_info(self.url, download=True, ie_key=self.ie_key)

        filename = self.outtmpl % {'ext':self.info['ext']}
        if not os.path.isfile(filename):
            filename = self.outtmpl % {'ext':'mkv'} # https://github.com/rg3/youtube-dl/issues/8349
            assert os.path.isfile(filename), 'Failed to determine the path of the downloaded video. Is the video too large?'

        ret = {
            'extractor': self.ie_key,
            'subtitles': {},
            'target': filename,
        }

        for key in self.info.get('subtitles', {}):
            filename = self.outtmpl % {'ext':key+'.srt'} # Postprocesed: converted to srt
            if os.path.isfile(filename):
                ret['subtitles'][key] = self.outtmpl % {'ext':key+'.srt'}

        return ret

    def progresshook(self, d):
        if d['status'] == 'downloading':
            percentage = int(100.0 * d['downloaded_bytes'] / d['total_bytes'])\
                if d['total_bytes'] else None
            self.statuscallback('Downloading to ' +\
                (d['tmpfilename'] or d['filename']), percentage)
        elif d['status'] == 'finished':
            self.statuscallback('Postprocessing...', -1)
        elif d['status'] == 'error':
            self.errorcallback('Error raised by YoutubeDL')

def download(url, ie_key, formats, subtitles, outputdir, statuscallback = None, errorcallback = None):
    job = Downloader(url, ie_key, formats, subtitles, outputdir, statuscallback, errorcallback)
    return job.run()
