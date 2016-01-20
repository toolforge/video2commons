#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# @adaptedfrom https://github.com/wikimedia/mediawiki-extensions-TimedMediaHandler/blob/master/TimedMediaHandler.php
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

# If the job runner should run transcode commands in a background thread and monitor the
# transcoding progress. This enables more fine grain control of the transcoding process, wraps
# encoding commands in a lower priority 'nice' call, and kills long running transcodes that are
# not making any progress. If set to false, the job runner will use the more compatible
# php blocking shell exec command.
wgEnableNiceBackgroundTranscodeJobs = True;
# The priority to be used with the nice transcode commands.
wgTranscodeBackgroundPriority = 19;

# The total amout of time a transcoding shell command can take:
wgTranscodeBackgroundTimeLimit = 3600 * 8
# Maximum amount of virtual memory available to transcoding processes in KB
# 2GB avconv, ffmpeg2theora mmap resources so virtual memory needs to be high enough
wgTranscodeBackgroundMemoryLimit = 4 * 1024 * 1024
# Maximum file size transcoding processes can create, in KB
wgTranscodeBackgroundSizeLimit = 3 * 1024 * 1024 # 3GB
# Number of threads to use in avconv for transcoding
wgFFmpegThreads = 8
# The location of ffmpeg2theora (transcoding)
# Set to false to use avconv/ffmpeg to produce Ogg Theora transcodes instead;
# beware this will disable Ogg skeleton metadata generation.
#wgFFmpeg2theoraLocation = '/usr/bin/ffmpeg2theora'
wgFFmpeg2theoraLocation = False # Disabled due to being unable to accept stdin properly
# Location of the avconv/ffmpeg binary (used to encode WebM and for thumbnails)
wgFFmpegLocation = '/usr/bin/avconv'
wgFFprobeLocation = '/usr/bin/avprobe'

def wfEscapeShellArg(*args):
    import pipes
    return " ".join([pipes.quote(str(arg)) for arg in args])

def wfFormatSize(num, suffix='B'):
    # Source: http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)

def wfFormatTimeHMS(s):
	m, s = divmod(s, 60)
	h, m = divmod(m, 60)
	return "%d:%02d:%02d" % (h, m, s)