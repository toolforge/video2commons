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
# along with self program.  If not, see <http://www.gnu.org/licenses/>
# 

import os
from transcodejob import WebVideoTranscodeJob
from transcode import WebVideoTranscode
from globals import *
from converter import Converter # https://github.com/senko/python-video-converter

def encode(source, key, statuscallback = None, errorcallback = None):
    source = os.path.abspath(source)
    target = source + '.' + key
    preserve = {'video':False, 'audio':False}

    c = Converter(ffmpeg_path=None, ffprobe_path=None)
    info = c.probe(source)

    targettype = WebVideoTranscode.derivativeSettings.get(key)
    if info and targettype:
        if info.video.codec == targettype.get('videoCodec'):
            preserve['video'] = True
        if info.audio.codec == targettype.get('audioCodec'):
            preserve['audio'] = True

    job = WebVideoTranscodeJob(source, target, key, preserve, statuscallback, errorcallback)
    job.run()

    return target

