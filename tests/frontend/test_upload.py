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

"""Tests related to the uploading of files to the flask app."""

import io

import pytest

from video2commons.frontend import api, upload
from video2commons.shared.validation import is_valid_filekey

CONTENT = b"content of the file"

# The server generates a uuid1, a client may choose a uuid4.
UUID1 = "123e4567-e89b-11d3-a456-426614174000"
UUID4 = "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
def uploads_dir(monkeypatch, tmp_path):
    """Store the uploads in a temporary directory."""
    monkeypatch.setattr(upload, "getpath", lambda filekey: str(tmp_path / filekey))
    return tmp_path


def post_upload(client, filename, **data):
    """Upload a file in one request, and get the JSON of the response."""
    response = client.post(
        "/api/upload/upload",
        data={"_csrf_token": "csrf", "file": (io.BytesIO(CONTENT), filename), **data},
    )
    return response.get_json()


@pytest.mark.parametrize(
    ("filename", "extension"),
    [("video.mp4", "mp4"), ("VIDEO.MOV", "mov"), ("clip.final.avi", "avi")],
)
def test_new_filekeys_keep_known_extensions(filename, extension):
    filekey = upload.new_filekey(filename)

    assert filekey.endswith(f".{extension}")
    assert is_valid_filekey(filekey)


@pytest.mark.parametrize(
    "filename",
    ["page.html", "image.svg", "clip.mkv", "archive.tar.gz", "noextension", "", None],
)
def test_new_filekeys_drop_other_extensions(filename):
    filekey = upload.new_filekey(filename)

    assert "." not in filekey
    assert is_valid_filekey(filekey)


def test_uploads_are_stored_under_a_new_filekey(client, uploads_dir):
    data = post_upload(client, "video.mp4")

    assert data["result"] == "Success"
    assert data["filekey"].endswith(".mp4")
    assert is_valid_filekey(data["filekey"])
    assert (uploads_dir / data["filekey"]).read_bytes() == CONTENT


@pytest.mark.parametrize("filename", ["page.html", "image.svg", "photo.jpeg"])
def test_uploads_drop_other_extensions(client, uploads_dir, filename):
    data = post_upload(client, filename)

    assert data["result"] == "Success"
    assert "." not in data["filekey"]
    assert [path.name for path in uploads_dir.iterdir()] == [data["filekey"]]


@pytest.mark.parametrize(
    "filekey", [UUID4, f"{UUID4}.mp4", f"{UUID4}.avi", f"{UUID4}.mov"]
)
def test_uploads_accept_valid_client_filekeys(client, uploads_dir, filekey):
    data = post_upload(client, "video", filekey=filekey)

    assert data["result"] == "Success"
    assert data["filekey"] == filekey
    assert (uploads_dir / filekey).read_bytes() == CONTENT


@pytest.mark.parametrize(
    "filekey",
    [f"{UUID4}.html", f"{UUID4}.svg", "upload.mp4", f"../{UUID4}", f"{UUID4}.mp4\n"],
)
def test_uploads_reject_invalid_client_filekeys(client, uploads_dir, filekey):
    data = post_upload(client, "video.mp4", filekey=filekey)

    assert data["step"] == "error"
    assert "Unacceptable file key" in data["error"]
    assert list(uploads_dir.iterdir()) == []


@pytest.mark.parametrize(
    "filekey", ["/etc/passwd", f"../{UUID1}", f"{UUID1}.html", "upload.mp4"]
)
def test_status_rejects_invalid_filekeys(api_post, filekey):
    data = api_post("upload/status", filekey=filekey)

    assert data["step"] == "error"
    assert "Unacceptable file key" in data["error"]


@pytest.mark.parametrize("queue", [None, api.DEFAULT_QUEUE])
@pytest.mark.parametrize("filekey", [f"{UUID1}.html", f"../{UUID1}", "upload.mp4"])
def test_tasks_reject_invalid_upload_filekeys(client, monkeypatch, filekey, queue):
    started = []
    monkeypatch.setattr(api, "run_task_internal", lambda *args: started.append(args))
    with client.session_transaction() as session:
        session["access_token_key"] = "key"
        session["access_token_secret"] = "secret"

    data = {
        "_csrf_token": "csrf",
        "url": f"uploads:{filekey}",
        "extractor": "",
        "subtitles": "false",
        "filename": "Example video",
        "filedesc": "Example description",
        "format": "webm (VP9/Opus)",
    }
    if queue:
        data["queue"] = queue
    response = client.post("/api/task/run", data=data)

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid file key format"}
    assert started == []
