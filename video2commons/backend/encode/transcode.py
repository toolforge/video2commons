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

"""
WebVideoTranscode provides settings.

@adaptedfrom Extension:TimedMediaHandler:
WebVideoTranscode/WebVideoTranscode.php under GPLv2
"""


class WebVideoTranscode:
    """
    Main WebVideoTranscode Class hold some config values.

    Encoding parameters are set via firefogg encode api

    For clarity and compatibility with passing down
    client side encode settings at point of upload

    http://firefogg.org/dev/index.html
    """

    settings = {
        "ogv": {
            "videoQuality": 7,
            "audioQuality": 6,
            "noUpscaling": "True",
            "twopass": "False",
            "optimize": "True",
            "keyframeInterval": "128",
            "videoCodec": "theora",
            "audioCodec": "vorbis",
            "type": 'video/ogg codecs="theora, vorbis"',
        },
        "an.ogv": {
            "videoQuality": 7,
            "noUpscaling": "True",
            "twopass": "False",
            "optimize": "True",
            "keyframeInterval": "128",
            "videoCodec": "theora",
            "noaudio": "True",
            "type": 'video/ogg codecs="theora, vorbis"',
        },
        # WebM transcode:
        "webm": {
            "crf": 10,
            "videoBitrate": "0",
            "audioQuality": 6,
            "noUpscaling": "True",
            "twopass": "True",
            "videoCodec": "vp8",
            "audioCodec": "vorbis",
            "type": 'video/webm codecs="vp8, vorbis"',
        },
        "an.webm": {
            "crf": 10,
            "videoBitrate": "0",
            "noUpscaling": "True",
            "twopass": "True",
            "videoCodec": "vp8",
            "noaudio": "True",
            "type": 'video/webm codecs="vp8, vorbis"',
        },
        # WebM VP9 transcode:
        "vp9.webm": {
            "crf": 35,
            "videoBitrate": "0",
            "audioBitrate": "128",
            "samplerate": "48000",
            "noUpscaling": "True",
            "twopass": "True",
            "altref": "True",
            "videoCodec": "vp9",
            "audioCodec": "opus",
            "tileColumns": "4",
            "speed": "2",
            "quality": "good",
            "type": 'video/webm codecs="vp9, opus"',
        },
        "an.vp9.webm": {
            "crf": 35,
            "videoBitrate": "0",
            "noUpscaling": "True",
            "twopass": "True",
            "altref": "True",
            "videoCodec": "vp9",
            "noaudio": "True",
            "tileColumns": "4",
            "speed": "2",
            "quality": "good",
            "type": 'video/webm codecs="vp9, opus"',
        },
        # WebM AV1 transcode:
        #
        # Presets: https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/CommonQuestions.md#what-presets-do
        # Multipass: https://github.com/HandBrake/HandBrake/issues/4831#issuecomment-1546617210
        "av1.webm": {
            "audioBitrate": "128",
            "audioCodec": "opus",
            "crf": 30,
            "preset": "6",
            "samplerate": "48000",
            "twopass": "False",  # twopass is not supported for AV1 with CRF
            "type": 'video/webm codecs="av01, opus"',
            "videoBitrate": "0",
            "videoCodec": "av1",
        },
        "an.av1.webm": {
            "crf": 30,
            "noaudio": "True",
            "preset": "6",
            "twopass": "False",  # twopass is not supported for AV1 with CRF
            "type": 'video/webm codecs="av01, opus"',
            "videoBitrate": "0",
            "videoCodec": "av1",
        },
        # Audio profiles
        "ogg": {
            "audioCodec": "vorbis",
            "audioQuality": "6",
            "samplerate": "44100",
            "channels": "2",
            "noUpscaling": "True",
            "novideo": "True",
            "type": 'audio/ogg codecs="vorbis"',
        },
        "opus": {
            "audioCodec": "opus",
            "audioBitrate": "128",
            "samplerate": "48000",
            "channels": "2",
            "noUpscaling": "True",
            "novideo": "True",
            "type": 'audio/ogg codecs="opus"',
        },
    }
