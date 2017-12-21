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

"""Convert and upload subtitles."""

from __future__ import absolute_import

import subprocess
import pywikibot
import pycountry
from converter import Converter
import chardet

from video2commons.exceptions import TaskAbort


def subtitles(task):
    """Convert and upload subtitles to corresponding TimedText pages."""
    percent = 0
    c = Converter(
        ffmpeg_path='/usr/bin/ffmpeg',
        ffprobe_path='/usr/bin/ffprobe'
    )

    for langcode, filename in task.results['download']['subtitles'].items():
        try:
            lang = (pycountry.languages.get(alpha_2=langcode) or
                    pycountry.languages.get(alpha_3=langcode))
            langname = lang and lang.name
            if langname:
                with task.status._pause():
                    task.status.text = 'Loading subtitle in ' + langname
                    task.status.percent = int(percent)
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
                    task.status.text = "Running cmd: %s" % cmd
                    subprocess.check_call(cmd, stderr=None)
                    filename = target

                f = open(filename)
                subtitletext = f.read()
                f.close()
                subtitletext = subtitletext.decode(
                    chardet.detect(subtitletext)['encoding']
                )

                percent += 50.0 / len(subtitles)
                with task.status._pause():
                    task.status.text = 'Uploading subtitle in ' + langname
                    task.status.percent = int(percent)

                # ENSURE PYWIKIBOT OAUTH PROPERLY CONFIGURED!
                site = pywikibot.Site(
                    'commons', 'commons', user=task.args.username)

                filename = task.results['upload'][0]
                page = pywikibot.Page(
                    site,
                    u'TimedText:' + filename +
                    u'.' + langcode.lower() + u'.srt'
                )
                page.text = subtitletext
                if not page.exists():
                    page.save(
                        summary=u'Import ' + langname + u' subtitles for ' +
                        '[[:File:' + filename + ']]',
                        minor=False
                    )

                percent += 50.0 / len(subtitles)
                with task.status._pause():
                    task.status.text = 'Uploading subtitle in ' + langname
                    task.status.percent = int(percent)

        except TaskAbort:
            raise
        except Exception as e:
            with task.status._pause():
                task.status.text = type(e).__name__ + ": " + str(e)
                task.status.percent = -1
