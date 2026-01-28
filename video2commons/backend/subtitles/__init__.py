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

import os
import traceback
import subprocess
import json
import pywikibot
import langcodes
from converter import Converter
import chardet

from ..encode.globals import ffmpeg_location, ffprobe_location
from video2commons.exceptions import TaskAbort
from langcodes import Language
from langcodes.tag_parser import LanguageTagError


def upload(site, filename, text, langcode, langname):
    """Upload subtitles to Wikimedia Commons."""
    page = pywikibot.Page(site, f'TimedText:{filename}.{langcode.lower()}.srt')
    page.text = text
    if not page.exists():
        page.save(
            summary=f'Import {langname} subtitles for [[:File:{filename}]]',
            minor=False
        )


def get_container_subtitle_languages(filepath):
    """Returns subtitle languages contained in a video container."""
    languages = set()

    result = subprocess.run([
        ffprobe_location,
        '-loglevel', 'error',
        '-select_streams', 's',
        '-show_entries', 'stream=index:stream_tags=language',
        '-of', 'json',
        filepath
    ], capture_output=True, text=True)

    if result.returncode != 0:
        return set()

    for stream in json.loads(result.stdout).get('streams', []):
        has_language = 'tags' in stream and 'language' in stream['tags']
        has_index = 'index' in stream

        # Skip unlabelled subtitles that have no language tag.
        if not has_language or not has_index:
            continue

        try:
            langcode = langcodes.standardize_tag(stream['tags']['language'])
        except LanguageTagError:
            continue  # Skip subtitles with invalid language tags.

        languages.add(langcode)

    return languages


def get_subtitle_languages(subtitles):
    """Returns subtitle languages identified by yt-dlp."""
    languages = set()

    for langcode, _ in subtitles.items():
        try:
            langcode = str(langcodes.get(langcode))
        except LanguageTagError:
            continue  # Skip subtitles with invalid language tags.

        languages.add(langcode)

    return languages

def upload_container_subtitles(filepath, filename, outputdir, username, statuscallback=None):
    """Extract subtitles from a video container that supports it (e.g. mkv)."""
    statuscallback = statuscallback or (lambda text, percent: None)

    statuscallback('Uploading subtitles...', -1)

    percent = 0

    result = subprocess.run([
        ffprobe_location,
        '-loglevel', 'error',
        '-select_streams', 's',
        '-show_entries', 'stream=index:stream_tags=language',
        '-of', 'json',
        filepath
    ], capture_output=True, text=True)

    if result.returncode != 0:
        statuscallback(
            f'Failed to extract subtitles: {result.stderr or result.returncode}',
            None
        )
        return

    subtitles = []
    languages = set()
    streams = json.loads(result.stdout).get('streams', [])

    if not streams:
        statuscallback('No subtitles found in container', 100)
        return

    statuscallback(f'Extracting subtitles for {len(streams)} language(s)...', -1)

    # Extract all subtitles from the video container (0-50%).
    for stream in streams:
        has_language = 'tags' in stream and 'language' in stream['tags']
        has_index = 'index' in stream

        # Skip unlabelled subtitles that have no language tag.
        if not has_language or not has_index:
            percent += 50.0 / len(streams)
            statuscallback('Skipping subtitles missing required tags', None)
            continue

        try:
            langcode = langcodes.standardize_tag(stream['tags']['language'])
        except LanguageTagError:
            percent += 50.0 / len(streams)
            statuscallback(
                f'Skipping subtitles with invalid language tag: {langcode}',
                None
            )
            continue  # Skip subtitles with invalid language tags.

        # Skip subtitles with the same language as previous subtitles since
        # this isn't supported by Mediawiki.
        if langcode in languages:
            percent += 50.0 / len(streams)
            statuscallback(
                f'Skipping duplicate subtitles with language: {langcode}',
                None
            )
            continue
        else:
            languages.add(langcode)

        langname = Language.make(language=langcode).display_name()
        statuscallback(f'Extracting {langname} subtitles...', int(percent))

        srt_filepath = os.path.join(outputdir, f'{filename}.{langcode.lower()}.srt')

        # Write the subtitles to the output directory of the job.
        result = subprocess.run([
            ffmpeg_location,
            '-nostdin',
            '-hide_banner',
            '-loglevel', 'quiet',
            '-i', filepath,
            '-map', f'0:{stream["index"]}',
            srt_filepath
        ], capture_output=True, text=True)

        percent += 50.0 / len(streams)

        if result.returncode != 0:
            statuscallback(
                f"Failed to extract '{langcode.lower()}' subtitles: {result.stderr or result.returncode}",
                int(percent)
            )
            continue

        subtitles.append((langcode, langname, srt_filepath))

    if not subtitles:
        statuscallback('No subtitles extracted successfully', 100)
        return

    # Attempt uploads only after successful extraction of all subtitles (50-100%).
    for langcode, langname, srt_filepath in subtitles:
        try:
            statuscallback(f'Uploading {langname} subtitles...', int(percent))

            with open(srt_filepath, 'rb') as f:
                text = f.read()

            # Try to first decode the subtitles as UTF-8 if possible rather
            # than relying entirely on chardet as it detects encodings
            # using a statistical method that is prone to error.
            decoded_text = parse_utf8(text)
            if decoded_text is not None:
                text = decoded_text
            else:
                # It's not UTF-8, so try to detect the encoding.
                encoding = chardet.detect(text)['encoding']
                if not encoding:
                    statuscallback(
                        f'Skipping subtitles with invalid encoding: {langcode}',
                        None
                    )
                    continue

                try:
                    text = text.decode(encoding)
                except Exception:
                    statuscallback(
                        f'Skipping subtitles with invalid encoding: {langcode}',
                        None
                    )
                    continue

            upload(
                site=pywikibot.Site('commons', 'commons', user=username),
                filename=filename,
                text=text,
                langcode=langcode,
                langname=langname
            )

            percent += 50.0 / len(subtitles)
            statuscallback(f'Finished uploading {langname} subtitles', int(percent))
        except TaskAbort:
            raise
        except Exception as e:
            percent += 50.0 / len(subtitles)
            statuscallback(f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}', int(percent))


def upload_subtitles(
    subtitles, wikifilename, username,
    statuscallback=None, errorcallback=None
):
    """Convert and upload subtitles to corresponding TimedText pages."""
    statuscallback = statuscallback or (lambda text, percent: None)
    errorcallback = errorcallback or (lambda text: None)

    statuscallback('Uploading subtitles...', -1)

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

            upload(
                site=site,
                filename=wikifilename,
                text=subtitletext,
                langcode=langcode,
                langname=langname
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


def parse_utf8(bytestring):
    """Try to decode a bytestring as UTF-8, returning None on failure."""
    try:
        return bytestring.decode('utf-8')
    except UnicodeDecodeError:
        return None
