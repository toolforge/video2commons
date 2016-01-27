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
import subprocess
import pywikibot
import pycountry # https://bitbucket.org/flyingcircus/pycountry
from converter import Converter # https://github.com/senko/python-video-converter
import chardet # https://github.com/chardet/chardet

class SubtitlesUploader(object):
    def __init__(self, subtitles, wikifilename, username,
            statuscallback = None, errorcallback = None):
        self.subtitles = subtitles
        self.wikifilename = wikifilename
        self.username = username
        self.statuscallback = statuscallback or (lambda text, percent: None)
        self.errorcallback = errorcallback or (lambda text: None)

    def run(self):
        percent = 0
        for lang, filename in self.subtitles.items():
            try:
                langname = self.lang(lang)
                if langname:
                    self.statuscallback('Loading subtitle in ' + langname, int(percent))
                    subtitletext = ''
                    format = self.format(filename)
                    if format.lower() != 'srt':
                        filename = self.transcode(filename, format)

                    f = open(filename)
                    subtitletext = f.read()
                    f.close()
                    subtitletext = subtitletext.decode(chardet.detect(subtitletext)['encoding'])

                    percent += 50.0 / len(self.subtitles)
                    self.statuscallback('Uploading subtitle in ' + langname, int(percent))

                    self.edit(u'TimedText:' + self.wikifilename.decode('utf-8') + u'.' + lang.lower() + u'.srt', subtitletext,\
                        u'Import ' + langname + u' subtitles for [[:File:' + self.wikifilename.decode('utf-8') + ']]')

                    percent += 50.0 / len(self.subtitles)
                    self.statuscallback('Finished processing subtitle in ' + langname, int(percent))

            except Exception, e:
                self.statuscallback(type(e).__name__ + ": " + str(e), None)
                print e
                pass

    @staticmethod
    def lang(langcode):
        lang = pycountry.languages.get(iso639_1_code=langcode) # For now
        return lang and lang.name

    @staticmethod
    def format(filename):
        c = Converter(ffmpeg_path='/usr/bin/ffmpeg', ffprobe_path='/usr/bin/ffprobe')
        info = c.probe(filename)
        if not info: return None
        if len(info.streams) != 1: return None
        if info.streams[0].type != 'subtitle': return None
        return info.streams[0].codec

    def transcode(self, filename, format):
        target = filename + '.srt'
        cmd = ['/usr/bin/ffmpeg', '-i', filename, '-f', 'srt', '-']
        self.statuscallback("Running cmd: %s" % cmd, None)
        return subprocess.check_output(cmd, stderr=None)

    def edit(self, title, text, summary):
        # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
        site = pywikibot.Site('commons', 'commons', user=self.username)
        page = pywikibot.Page(site, title)
        page.text = text
        if not page.exists(): page.save(summary=summary, minor=False)


def subtitles(subtitles, wikifilename, username, statuscallback = None, errorcallback = None):
    job = SubtitlesUploader(subtitles, wikifilename, username, statuscallback, errorcallback)
    job.run()