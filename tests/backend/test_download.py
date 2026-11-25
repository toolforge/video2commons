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

"""Tests related to the downloading of files by the worker."""

import pytest

from video2commons.backend import download
from video2commons.exceptions import TaskError

UUID1 = "123e4567-e89b-11d3-a456-426614174000"


def fail_to_download(*args, **kwargs):
    raise AssertionError("The worker must not download this URL")


@pytest.mark.parametrize(
    "filekey", [f"{UUID1}.html", f"../{UUID1}", "upload.mp4", "../../config"]
)
def test_downloads_reject_invalid_upload_filekeys(monkeypatch, tmp_path, filekey):
    monkeypatch.setattr(download, "YoutubeDLRateLimited", fail_to_download)

    with pytest.raises(TaskError, match="Invalid file key format"):
        download.download(
            None, f"uploads:{filekey}", None, "best", False, str(tmp_path)
        )
