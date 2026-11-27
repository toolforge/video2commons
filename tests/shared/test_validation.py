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

"""Tests for the filekeys that uploads may be stored and served under."""

import pytest

from video2commons.shared.validation import (
    KNOWN_EXTENSIONS,
    is_known_extension,
    is_valid_filekey,
)

# The server generates a uuid1, a client may choose a uuid4.
UUID1 = "123e4567-e89b-11d3-a456-426614174000"
UUID4 = "123e4567-e89b-42d3-a456-426614174000"


@pytest.mark.parametrize("extension", ["avi", "m4v", "mov", "mp4", "qt"])
def test_handled_extensions_are_known(extension):
    assert is_known_extension(extension)


@pytest.mark.parametrize("extension", ["", "html", "svg", "mkv", "mp3"])
def test_other_extensions_are_not_known(extension):
    assert not is_known_extension(extension)


@pytest.mark.parametrize("filekey", [UUID1, UUID4])
def test_uuids_without_an_extension_are_valid(filekey):
    assert is_valid_filekey(filekey)


@pytest.mark.parametrize("extension", sorted(KNOWN_EXTENSIONS))
def test_known_extensions_are_valid(extension):
    assert is_valid_filekey(f"{UUID1}.{extension}")


@pytest.mark.parametrize(
    "extension",
    ["html", "htm", "xhtml", "svg", "xml", "js", "css", "pdf", "swf", "ts", "jpeg"],
)
def test_other_extensions_are_invalid(extension):
    assert not is_valid_filekey(f"{UUID1}.{extension}")


@pytest.mark.parametrize(
    "filekey",
    [
        "",
        "upload.mp4",
        UUID1[:-1],
        UUID1.upper(),
        f"{UUID1}.",
        f"{UUID1}.MP4",
        f"{UUID1}.mp4.html",
        f"{UUID1}.html.mp4",
        f"{UUID1}\n",
        f"{UUID1}.mp4\n",
        f" {UUID1}",
        f"{UUID1}\x00.mp4",
        f"../{UUID1}",
        f"/etc/{UUID1}",
        f"{UUID1}/../upload.mp4",
        f"{UUID1}.mp4/",
    ],
)
def test_malformed_filekeys_are_invalid(filekey):
    assert not is_valid_filekey(filekey)
