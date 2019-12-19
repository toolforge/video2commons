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

"""Convert and upload subtitles."""



import subprocess
import pywikibot
import langcodes
from converter import Converter
import chardet

from video2commons.exceptions import TaskAbort


def subtitles(
    subtitles, wikifilename, username,
    statuscallback=None, errorcallback=None
):
    """Convert and upload subtitles to corresponding TimedText pages."""
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)

    percent = 0
    c = Converter(
        ffmpeg_path='/usr/bin/ffmpeg',
        ffprobe_path='/usr/bin/ffprobe'
    )

    for langcode, filename in subtitles.items():
        try:
            lang = langcodes.get(langcode)
            langcode = str(lang).lower()

            langdesc = lang.describe()
            langname = langdesc['language']
            del langdesc['language']
            if langdesc:
                langname += ' (%s)' % ', '.join(langdesc.values())

            statuscallback('Loading subtitle in ' + langname, int(percent))
            subtitletext = ''

            info = c.probe(filename)
            if not info:
                continue
            if len(info.streams) != 1:
                continue
            if info.streams[0].type != 'subtitle':
                continue
            format = info.streams[0].codec

            if format.lower() != 'srt':
                target = filename + '.srt'
                cmd = [
                    '/usr/bin/ffmpeg',
                    '-i', filename,
                    '-f', 'srt',
                    target
                ]
                statuscallback("Running cmd: %s" % cmd, None)
                subprocess.check_call(cmd, stderr=None)
                filename = target

            f = open(filename)
            subtitletext = f.read()
            f.close()
            subtitletext = subtitletext.decode(
                chardet.detect(subtitletext)['encoding']
            )

            percent += 50.0 / len(subtitles)
            statuscallback(
                'Uploading subtitle in ' + langname,
                int(percent)
            )

            # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
            site = pywikibot.Site('commons', 'commons', user=username)
            page = pywikibot.Page(
                site,
                'TimedText:' + wikifilename.decode('utf-8') +
                '.' + langcode.lower() + '.srt'
            )
            page.text = subtitletext
            if not page.exists():
                page.save(
                    summary='Import ' + langname + ' subtitles for ' +
                    '[[:File:' + wikifilename.decode('utf-8') + ']]',
                    minor=False
                )

            percent += 50.0 / len(subtitles)
            statuscallback(
                'Finished processing subtitle in ' + langname,
                int(percent)
            )
        except TaskAbort:
            raise
        except Exception as e:
            statuscallback(type(e).__name__ + ": " + str(e), None)
            pass
