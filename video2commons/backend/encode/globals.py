#!/usr/bin/python
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

"""
Configurations and helper functions.

@adaptedfrom Extension:TimedMediaHandler: TimedMediaHandler.php
"""

# The priority to be used with the nice transcode commands.
background_priority = 19

# The total amout of time a transcoding shell command can take:
background_time_limit = 3600 * 24 * 2  # 2 days
# Maximum amount of virtual memory available to transcoding processes in KB
# 2GB avconv
background_memory_limit = 8 * 1024 * 1024  # 8GB
# Maximum file size transcoding processes can create, in KB
background_size_limit = 10 * 1024 * 1024  # 10GB
# Number of threads to use in avconv for transcoding
ffmpeg_threads = 0  # optimal
# Location of the avconv/ffmpeg binary (used to encode WebM and for thumbnails)
ffmpeg_location = '/usr/bin/ffmpeg'
ffprobe_location = '/usr/bin/ffprobe'


def escape_shellarg(*args):
    """Escape shell arguments."""
    import pipes
    return " ".join([pipes.quote(str(arg)) for arg in args])


def format_size(num, suffix='B'):
    """Format the size with prefixes."""
    # Source: StackOverflow
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)


def format_time(s):
    """Format the time from number of seconds."""
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return "%d:%02d:%02d" % (h, m, s)


def time_to_seconds(time):
    """Get the number of seconds from time expression."""
    return \
        sum([a * b for a, b in zip([3600, 60, 1], map(int, time.split(':')))])
