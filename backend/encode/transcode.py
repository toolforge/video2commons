#not /usr/bin/python
# -*- coding: UTF-8 -*-
#
# WebVideoTranscode provides:
#  encode keys
#  encode settings
#
#     extends api to return all the streams
#  extends video tag output to provide all the available sources
#
# @adaptedfrom https://github.com/wikimedia/mediawiki-extensions-TimedMediaHandler/blob/master/WebVideoTranscode/WebVideoTranscode.php under GPLv2
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

import os, sys

class WebVideoTranscode:
    """
    Main WebVideoTranscode Class hold some constants and config values
    """

    """
    Key constants for the derivatives,
    this key is appended to the derivative file name
    
    If you update the wgDerivativeSettings for one of these keys
    and want to re-generate the video you should also update the
    key constant. ( Or just run a maintenance script to delete all
    the assets for a given profile )
    
    Msg keys for derivatives are set as follows:
    messages['timedmedia-derivative-200_200kbs.ogv']: 'Ogg 200'
    """
    # Ogg Profiles
    ENC_OGV = 'ogv'
    ENC_NOAUDIO_OGV = 'an.ogv'

    # WebM VP8/Vorbis profiles:
    ENC_WEBM = 'webm'
    ENC_NOAUDIO_WEBM = 'an.webm'

    # WebM VP9/Opus profiles:
    ENC_VP9 = 'vp9.webm'
    ENC_NOAUDIO_VP9 = 'an.vp9.webm'

    # mp4 profiles:
    #ENC_H264 = 'mp4'

    ENC_OGG_VORBIS = 'ogg'
    ENC_OGG_OPUS = 'opus'
    #ENC_MP3 = 'mp3'
    #ENC_AAC = 'm4a'

    # Static cache of transcode state per instantiation
    transcodeState = {}

    """
    Encoding parameters are set via firefogg encode api
    
    For clarity and compatibility with passing down
    client side encode settings at point of upload
    
    http://firefogg.org/dev/index.html
    """
    derivativeSettings = {
        ENC_OGV:
            {
                'videoQuality':                7,
                'audioQuality':                6,
                'noUpscaling':                 'True',
                'twopass':                     'False', # will be overridden by wgTmhTheoraTwoPassEncoding
                'optimize':                    'True',
                'keyframeInterval':            '128',
                'videoCodec':                  'theora',
                'audioCodec':                  'vorbis',
                'type':                        'video/ogg codecs="theora, vorbis"',
            },
        ENC_NOAUDIO_OGV:
            {
                'videoQuality':                7,
                'noUpscaling':                 'True',
                'twopass':                     'False', # will be overridden by wgTmhTheoraTwoPassEncoding
                'optimize':                    'True',
                'keyframeInterval':            '128',
                'videoCodec':                  'theora',
                'noaudio':                     'True',
                'type':                        'video/ogg codecs="theora, vorbis"',
            },

        # WebM transcode:
        ENC_WEBM:
            {
                'videoQuality':                7,
                'audioQuality':                6,
                'noUpscaling':                 'True',
                'twopass':                     'True',
                'videoCodec':                  'vp8',
                'audioCodec':                  'vorbis',
                'type':                        'video/webm codecs="vp8, vorbis"',
            },
        ENC_NOAUDIO_WEBM:
            {
                'videoQuality':                7,
                'noUpscaling':                 'True',
                'twopass':                     'True',
                'videoCodec':                  'vp8',
                'noaudio':                     'True',
                'type':                        'video/webm codecs="vp8, vorbis"',
            },

        # WebM VP9 transcode:
        ENC_VP9:
            {
                'videoQuality':                7,
                'audioQuality':                6,
                'noUpscaling':                 'True',
                'twopass':                     'True',
                'videoCodec':                  'vp9',
                'audioCodec':                  'opus',
                'tileColumns':                 '4',
                'type':                        'video/webm codecs="vp9, opus"',
            },
        ENC_NOAUDIO_VP9:
            {
                'videoQuality':                7,
                'noUpscaling':                 'True',
                'twopass':                     'True',
                'videoCodec':                  'vp9',
                'noaudio':                     'True',
                'tileColumns':                 '4',
                'type':                        'video/webm codecs="vp9, opus"',
            },

        # Audio profiles
        ENC_OGG_VORBIS:
            {
                'audioCodec':                  'vorbis',
                'audioQuality':                '1',
                'samplerate':                  '44100',
                'channels':                    '2',
                'noUpscaling':                 'True',
                'novideo':                     'True',
                'type':                        'audio/ogg codecs="vorbis"',
            },
        ENC_OGG_OPUS:
            {
                'audioCodec':                  'opus',
                'audioQuality':                '1',
                'samplerate':                  '44100',
                'channels':                    '2',
                'noUpscaling':                 'True',
                'novideo':                     'True',
                'type':                        'audio/ogg codecs="opus"',
            },
    }

