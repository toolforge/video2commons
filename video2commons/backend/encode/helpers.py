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

"""Helper function for the encode module."""


def get_video(info):
    """Returns the first video stream from a MediaInfo object.

    This exists to workaround a bug with the Converter library where the video
    property will erroneously select audio streams for some videos.
    """
    if not info:
        return None

    for stream in info.streams:
        if stream.type == "video":
            return stream

    return None
