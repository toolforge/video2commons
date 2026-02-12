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

"""Shared yt-dlp helpers used by both the worker app and the flask app."""

import os

from video2commons.config import tooldir


def add_youtube_params(params):
    """Adds YouTube authentication parameters to yt-dlp request params."""
    params = params.copy()

    cookies_path = tooldir + "/../cookies.txt"
    if os.path.isfile(cookies_path):
        params["cookiefile"] = cookies_path

    return params
