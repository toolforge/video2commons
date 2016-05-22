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

"""
Job for web video transcode.

Support two modes
1) non-free media transcode (delays the media file being inserted,
   adds note to talk page once ready)
2) derivatives for video (makes new sources for the asset)

@adaptedfrom Extension:TimedMediaHandler:
WebVideoTranscode/WebVideoTranscodeJob.php under GPLv2
"""

import os
import re
import math
import time
import subprocess
import signal
from transcode import WebVideoTranscode
from globals import (
    background_priority, background_time_limit, background_memory_limit,
    background_size_limit, ffmpeg_threads, ffmpeg_location, escape_shellarg,
    time_to_seconds
)

from video2commons.exceptions import TaskAbort


class WebVideoTranscodeJob(object):
    """Job class."""

    def __init__(
        self, source, target, key, preserve={},
        statuscallback=None, errorcallback=None
    ):
        """Initialize the instance."""
        self.source = os.path.abspath(source)
        self.target = os.path.abspath(target)
        self.key = key
        self.preserve = {'video': False, 'audio': False}
        self.preserve.update(preserve)
        self.statuscallback = statuscallback or (lambda text, percent: None)
        self.errorcallback = errorcallback or (lambda text: None)
        self.removeDuplicates = True

    def output(self, msg):
        """
        Output to statuscallback and stdout.

        @param msg string
        """
        msg = msg.strip()
        self.statuscallback(msg, None)
        print msg

    def get_file(self):
        """
        Get the target file.

        @return File
        """
        if not hasattr(self, 'file'):
            self.file = open(self.source, 'r')
            self.file.close()

        return self.file

    def get_target_path(self):
        """
        Get the target file path.

        @return string
        """
        if not hasattr(self, 'targetEncodeFile'):
            self.targetEncodeFile = open(self.target, 'w')
            self.targetEncodeFile.close()

        return self.targetEncodeFile.name

    def get_source_path(self):
        """
        Get the source file path.

        @return string|bool
        """
        if not hasattr(self, 'sourceFilePath'):
            self.sourceFilePath = self.get_file().name

        return self.sourceFilePath

    def set_error(self, error, transcode_key=None):
        """
        Update the transcode table with failure time and error.

        @param transcode_key string
        @param error string
        """
        self.errorcallback(error)

    def run(self):
        """
        Run the transcode request.

        @return boolean success
        """
        # get a local pointer to the file
        file = self.get_file()

        # Validate the file exists:
        if not file:
            self.set_error(self.source + ': File not found ')
            return False

        # Validate the transcode key param:
        transcode_key = self.key
        # Build the destination target
        if transcode_key not in WebVideoTranscode.settings:
            error = "Transcode key transcode_key not found, skipping"
            self.set_error(error)
            return False

        # Validate the source exists:
        if not self.get_source_path() or not \
                os.path.isfile(self.get_source_path()):
            status = self.source + ': Source not found'
            self.set_error(status, transcode_key)
            return False

        options = WebVideoTranscode.settings[transcode_key]

        if 'novideo' in options:
            self.output("Encoding to audio codec: " + options['audioCodec'])
        else:
            self.output("Encoding to codec: " + options['videoCodec'])

        # Check the codec see which encode method to call
        if 'novideo' in options or self.preserve['video']:
            status = self.ffmpeg_encode(options)
        elif options['videoCodec'] in ['vp8', 'vp9', 'h264'] or \
                (options['videoCodec'] == 'theora'):
            # Check for twopass:
            if 'twopass' in options and options['twopass'] == 'True':
                # ffmpeg requires manual two pass
                status = self.ffmpeg_encode(options, 1)
                if status and not isinstance(status, basestring):
                    status = self.ffmpeg_encode(options, 2)
            else:
                status = self.ffmpeg_encode(options)
        else:
            self.output('Error unknown codec:' + options['videoCodec'])
            status = 'Error unknown target codec:' + options['videoCodec']

        self.remove_ffmpeg_log_files()

        # If status is oky and target does not exist, reset status
        if status is True and not os.path.isfile(self.get_target_path()):
            status = 'Target does not exist: ' + self.get_target_path()

        # If status is ok and target is larger than 0 bytes
        if status is True and os.path.getsize(self.get_target_path()) > 0:
            pass  # Done
        else:
            # Update the transcode table with failure time and error
            self.set_error(status, transcode_key)

        return status is True

    def remove_ffmpeg_log_files(self):
        """Remove any log files."""
        path = self.get_target_path()
        dir = os.path.dirname(path.rstrip(os.pathsep))
        if os.path.isdir(dir):
            for file in os.listdir(dir):
                log_path = os.path.abspath(dir + "/" + file)
                ext = file.split('.')[-1]
                if ext == 'log' and log_path.startswith(path):
                    os.unlink(log_path)

    def ffmpeg_encode(self, options, p=0):
        """
        Utility helper for ffmpeg and ffmpeg2theora mapping.

        @param options array
        @param p int
        @return bool|string
        """
        if not os.path.isfile(self.get_source_path()):
            return "source file is missing, " + self.get_source_path() + \
                ". Encoding failed."

        # Set up the base command
        cmd = escape_shellarg(ffmpeg_location) + ' -y -i ' + \
            escape_shellarg(self.get_source_path())

        if 'vpre' in options:
            cmd += ' -vpre ' + escape_shellarg(options['vpre'])

        if 'novideo' in options:
            cmd += " -vn "
        elif self.preserve['video']:
            cmd += " -vcodec copy"
        elif options['videoCodec'] == 'vp8' or options['videoCodec'] == 'vp9':
            cmd += self.ffmpeg_add_webm_video_options(options, p)
        elif options['videoCodec'] == 'h264':
            cmd += self.ffmpeg_add_h264_video_options(options, p)
        elif options['videoCodec'] == 'theora':
            cmd += self.ffmpeg_add_theora_video_options(options, p)

        # Check for start time
        if 'starttime' in options:
            cmd += ' -ss ' + escape_shellarg(options['starttime'])
        else:
            options['starttime'] = 0

        # Check for end time:
        if 'endtime' in options:
            cmd += ' -t ' + str(options['endtime']) - str(options['starttime'])

        if p == 1 or 'noaudio' in options:
            cmd += ' -an'
        elif self.preserve['audio']:
            cmd += " -acodec copy"
        else:
            cmd += self.ffmpeg_add_audio_options(options, p)

        if p != 0:
            cmd += " -pass " + escape_shellarg(p)
            cmd += " -passlogfile " + \
                escape_shellarg(self.get_target_path() + '.log')

        # And the output target:
        if p == 1:
            cmd += ' /dev/null'
        else:
            cmd += " " + escape_shellarg(self.get_target_path())

        self.output("Running cmd: " + cmd + "\n")

        # Right before we output remove the old file
        retval, shellOutput = self.run_shell_exec(cmd, track=p != 1)

        if int(retval) != 0:
            return cmd + \
                "\nExitcode: " + str(retval)

        return True

    def ffmpeg_add_h264_video_options(self, options, p):
        """
        Add ffmpeg shell options for h264.

        @param options
        @param p
        @return string
        """
        # Set the codec:
        cmd = " -threads " + str(ffmpeg_threads) + " -vcodec libx264"

        if 'videoBitrate' in options:
            cmd += " -b " + escape_shellarg(options['videoBitrate'])

        # Output mp4
        cmd += " -f mp4"
        return cmd

    def ffmpeg_add_webm_video_options(self, options, p):
        """
        Add ffmpeg shell options for webm.

        @param options
        @param p
        @return string
        """
        cmd = ' -threads ' + str(ffmpeg_threads)

        # check for presets:
        if 'preset' in options:
            if options['preset'] == "360p":
                cmd += " -vpre libvpx-360p"
            elif options['preset'] == "720p":
                cmd += " -vpre libvpx-720p"
            elif options['preset'] == "1080p":
                cmd += " -vpre libvpx-1080p"

        # Add the boiler plate vp8 ffmpeg command:
        cmd += " -skip_threshold 0 -bufsize 6000k -rc_init_occupancy 4000"

        # Check for video quality:
        if 'videoQuality' in options and options['videoQuality'] >= 0:
            # Map 0-10 to 63-0, higher values worse quality
            quality = 63 - int(int(options['videoQuality']) / 10.0 * 63)
            cmd += " -qmin " + escape_shellarg(quality)
            cmd += " -qmax " + escape_shellarg(quality)

        # Check for video bitrate:
        if 'videoBitrate' in options:
            cmd += " -qmin 1 -qmax 51"
            cmd += " -vb " + escape_shellarg(options['videoBitrate'] * 1000)

        # Set the codec:
        if options['videoCodec'] == 'vp9':
            cmd += " -vcodec libvpx-vp9"
            if 'tileColumns' in options:
                cmd += ' -tile-columns ' + \
                    escape_shellarg(options['tileColumns'])
        else:
            cmd += " -vcodec libvpx"

        # Check for keyframeInterval
        if 'keyframeInterval' in options:
            cmd += ' -g ' + escape_shellarg(options['keyframeInterval'])
            cmd += ' -keyint_min ' + \
                escape_shellarg(options['keyframeInterval'])

        if 'deinterlace' in options:
            cmd += ' -deinterlace'

        # Output WebM
        cmd += " -f webm"

        return cmd

    def ffmpeg_add_theora_video_options(self, options, p):
        """
        Add ffmpeg shell options for ogg.

        Warning: does not create Ogg skeleton metadata track.

        @param options
        @param p
        @return string
        """
        cmd = ' -threads ' + str(ffmpeg_threads)

        # Check for video quality:
        if 'videoQuality' in options and options['videoQuality'] >= 0:
            cmd += " -q:v " + escape_shellarg(options['videoQuality'])

        # Check for video bitrate:
        if 'videoBitrate' in options:
            cmd += " -qmin 1 -qmax 51"
            cmd += " -vb " + escape_shellarg(options['videoBitrate'] * 1000)

        # Set the codec:
        cmd += " -vcodec theora"

        # Check for keyframeInterval
        if 'keyframeInterval' in options:
            cmd += ' -g ' + escape_shellarg(options['keyframeInterval'])
            cmd += ' -keyint_min ' + \
                escape_shellarg(options['keyframeInterval'])

        if 'deinterlace' in options:
            cmd += ' -deinterlace'

        if 'framerate' in options:
            cmd += ' -r ' + escape_shellarg(options['framerate'])

        # Output Ogg
        cmd += " -f ogg"

        return cmd

    def ffmpeg_add_audio_options(self, options, p):
        """
        Add ffmpeg shell options for audio.

        @param options array
        @param p
        @return string
        """
        cmd = ''
        if 'audioQuality' in options:
            cmd += " -aq " + escape_shellarg(options['audioQuality'])

        if 'audioBitrate' in options:
            cmd += ' -ab ' + str(options['audioBitrate']) * 1000

        if 'samplerate' in options:
            cmd += " -ar " + escape_shellarg(options['samplerate'])

        if 'channels' in options:
            cmd += " -ac " + escape_shellarg(options['channels'])

        if 'audioCodec' in options:
            encoders = {
                'vorbis': 'libvorbis',
                'opus': 'libopus',
                'mp3': 'libmp3lame',
            }
            if options['audioCodec'] in encoders:
                codec = encoders[options['audioCodec']]
            else:
                codec = options['audioCodec']

            cmd += " -acodec " + escape_shellarg(codec)
            if codec == 'aac':
                # the aac encoder is currently "experimental" in libav 9? :P
                cmd += ' -strict experimental'
        else:
            # if no audio codec set use vorbis :
            cmd += " -acodec libvorbis "

        return cmd

    def run_shell_exec(self, cmd, track=True):
        """
        Run the shell exec command.

        @param cmd String Command to be run
        @return int, string
        """
        cmd = 'ulimit -f ' + escape_shellarg(background_size_limit) + ';' + \
            'ulimit -v ' + escape_shellarg(background_memory_limit) + ';' + \
            'ulimit -t ' + escape_shellarg(background_time_limit) + ';' + \
            'ulimit -a;' + \
            'nice -n ' + escape_shellarg(background_priority) + ' ' + cmd + \
            ' 2>&1'

        # Adapted from https://gist.github.com/marazmiki/3015621
        process = subprocess.Popen(
            cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, shell=True, preexec_fn=os.setsid
        )

        re_duration = re.compile(r'Duration: (\d{2}:\d{2}:\d{2})')
        re_position = re.compile(r'time=(\d{2}:\d{2}:\d{2})', re.I)

        duration = None
        position = None
        newpercentage = percentage = -1

        while process.poll() is None:
            # for line in process.stdout.readlines():
            # http://bugs.python.org/issue3907
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                print line,

                if track:
                    if duration is None:
                        duration_match = re_duration.search(line)
                        if duration_match:
                            duration = time_to_seconds(duration_match.group(1))
                    else:
                        position_match = re_position.search(line)
                        if position_match:
                            position = time_to_seconds(position_match.group(1))
                            if duration and position:
                                newpercentage = min(int(
                                    math.floor(100 * position / duration)
                                ), 100)

                    if newpercentage != percentage:
                        percentage = newpercentage
                        try:
                            self.statuscallback(None, percentage)
                        except TaskAbort:
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                            raise

            time.sleep(2)

        return process.returncode, ''
