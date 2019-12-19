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

"""Main encode module."""

import collections
import json
import os
import subprocess

from .transcodejob import WebVideoTranscodeJob
from .transcode import WebVideoTranscode
from .globals import ffprobe_location


Info = collections.namedtuple('Info', 'video audio')
Stream = collections.namedtuple('Stream', 'codec')


def ffprobe(path):
    ffprobe_data = subprocess.check_output([
        ffprobe_location,
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        path
    ], encoding='utf-8')

    ffprobe_data = json.loads(ffprobe_data)

    if not ffprobe_data.get('streams'):
        return None

    info = Info(*([None] * len(Info._fields)))

    for stream in ffprobe_data['streams']:
        if stream['codec_type'] not in Info._fields:
            continue
        if getattr(info.video, stream['codec_type']):
            continue

        s = Stream(codec=stream['codec_name'])
        info = info._replace(**{stream['codec_type']: s})

    return info


def encode(source, origkey, statuscallback=None, errorcallback=None):
    """Main encode function."""
    source = os.path.abspath(source)
    preserve = {'video': False, 'audio': False}

    info = ffprobe(source)

    targettype = WebVideoTranscode.settings.get(origkey)
    key = getbestkey(info, targettype) or origkey
    targettype = WebVideoTranscode.settings.get(key)

    if info and targettype:
        if info.video and info.video.codec == targettype.get('videoCodec'):
            preserve['video'] = True
        if info.audio and info.audio.codec == targettype.get('audioCodec'):
            preserve['audio'] = True

    target = source + '.' + key
    job = WebVideoTranscodeJob(
        source, target, key, preserve, statuscallback, errorcallback
    )

    return target if job.run() else None


def getbestkey(info, targettype):
    """Find the bext convert key to use."""
    # Asserts
    assert info, 'The file format could not be recognized'
    assert targettype, 'The target format is invalid.'
    assert info.video or info.audio, 'The file has no video or audio tracks.'
    assert info.video or not targettype.get('videoCodec'), \
        'Video is asked to be kept but the file has no video tracks.'
    assert info.audio or not targettype.get('audioCodec'), \
        'Audio is asked to be kept but the file has no audio tracks.'

    if targettype.get('videoCodec') and targettype.get('audioCodec'):
        # need both video & audio -- no codec change in video & audio
        for newkey, newtargettype in WebVideoTranscode.settings.items():
            if info.video.codec == newtargettype.get('videoCodec') and \
                    info.audio.codec == newtargettype.get('audioCodec'):
                return newkey

    elif targettype.get('videoCodec') and 'noaudio' in targettype:
        # need video only -- no codec change in video & remove audio
        for newkey, newtargettype in WebVideoTranscode.settings.items():
            if info.video.codec == newtargettype.get('videoCodec') and \
                    'noaudio' in newtargettype:
                return newkey

    elif 'novideo' in targettype and targettype.get('audioCodec'):
        # need video only -- no codec change in audio & remove video
        for newkey, newtargettype in WebVideoTranscode.settings.items():
            if info.audio.codec == newtargettype.get('audioCodec') and \
                    'novideo' in newtargettype:
                return newkey

    return None
