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

import traceback
import subprocess
import pywikibot
import langcodes
from converter import Converter
import chardet

from ..encode.globals import ffmpeg_location, ffprobe_location
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
        ffmpeg_path=ffmpeg_location,
        ffprobe_path=ffprobe_location
    )

    for langcode, filename in list(subtitles.items()):
        try:
            lang = langcodes.get(langcode)
            langcode = str(lang).lower()

            langdesc = lang.describe()
            langname = langdesc['language']
            del langdesc['language']
            if langdesc:
                langname += ' (%s)' % ', '.join(list(langdesc.values()))

            statuscallback('Loading subtitles in ' + langname, int(percent))
            subtitletext = ''

            info = c.probe(filename)
            if not info:
                continue
            if len(info.streams) != 1:
                continue
            if info.streams[0].type != 'subtitle':
                continue
            format = info.streams[0].codec

            if format.lower() != 'subrip':
                target = filename + '.srt'
                cmd = [
                    ffmpeg_location,
                    '-i', filename,
                    '-f', 'srt',
                    target
                ]
                statuscallback("Running cmd: %s" % cmd, None)
                subprocess.check_call(cmd, stderr=None)
                filename = target

            with open(filename, 'rb') as f:
                subtitletext = f.read()

            subtitletext = subtitletext.decode(
                chardet.detect(subtitletext)['encoding']
            )

            percent += 50.0 / len(subtitles)
            statuscallback(
                'Uploading subtitles in ' + langname,
                int(percent)
            )

            # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
            site = pywikibot.Site('commons', 'commons', user=username)
            page = pywikibot.Page(
                site,
                f'TimedText:{wikifilename}.{langcode.lower()}.srt'
            )
            page.text = subtitletext
            if not page.exists():
                page.save(
                    summary=f'Import {langname} subtitles for [[:File:{wikifilename}]]',
                    minor=False
                )

            percent += 50.0 / len(subtitles)
            statuscallback(
                'Finished processing subtitles in ' + langname,
                int(percent)
            )
        except TaskAbort:
            raise
        except Exception as e:
            statuscallback(f'{type(e).__name__}: {e} \n\n{traceback.format_exc()}', None)
            pass
