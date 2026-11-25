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

"""Validation helpers used by both the worker app and the flask app."""

import re

# An upload is served to the workers with the Content-Type related to its
# filekey's extension, so only extensions with known special handling are
# allowed. Specifically those are the ones the worker has download size limits
# for, and also extensions used by known API consumers like Spacemedia.
KNOWN_EXTENSIONS = frozenset({"avi", "m4v", "mov", "mp4", "qt"})

RE_FILEKEY = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(?:\.([a-z0-9]+))?"
)


def is_known_extension(extension):
    """Check if an extension is one that v2c has special handling for."""
    return extension in KNOWN_EXTENSIONS


def is_valid_filekey(filekey):
    """Check if a filekey is a UUID with an (optional) known extension."""
    uuid_match = RE_FILEKEY.fullmatch(filekey)
    if not uuid_match:
        return False

    extension = uuid_match.group(1)
    return extension is None or is_known_extension(extension)
