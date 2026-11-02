"""Local agent protocol tests, without YouTube, Commons or production Redis.

Run: uv run --with flask --with redis --with 'fakeredis[lua]' --with requests
     --with 'yt-dlp[default]' python -m unittest discover -s tests -p 'test_*.py'
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import fakeredis
import requests
from flask import Flask, session
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    # Import the isolated protocol without initializing the production frontend
    # package (which connects to Commons and imports the Celery worker).
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load_module("local_agent_server", "video2commons/frontend/local_agent.py")
agent = load_module("local_agent_client", "video2commons/frontend/desktop_agent.py")
redisession = load_module("redisession_test", "video2commons/frontend/redisession.py")
URL = "https://www.youtube.com/watch?v=abcdefghijk"


class FlaskTransport(requests.adapters.BaseAdapter):
    """Run the actual requests client against the Flask protocol routes."""

    def __init__(self, app):
        self.client = app.test_client()

    def send(self, request, **kwargs):
        result = self.client.open(
            request.path_url,
            method=request.method,
            data=request.body,
            headers=dict(request.headers),
            base_url="https://localhost",
        )
        response = requests.Response()
        response.status_code = result.status_code
        response._content = result.data
        response.headers.update(result.headers)
        response.request = request
        response.url = request.url
        return response

    def close(self):
        pass


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.conn = fakeredis.FakeRedis(decode_responses=True)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.info = {
            "id": "abcdefghijk",
            "title": "Example video",
            "description": "Test",
            "license": server.CC_LICENSE,
            "upload_date": "20260901",
            "uploader": "Author",
            "uploader_url": "https://www.youtube.com/@author",
            "height": 1080,
            "width": 1920,
            "tbr": 1000,
        }
        self.describe = Mock(
            return_value={
                "filename": "Example video",
                "filedesc": "Test source and license",
                "date": "2026-09-01",
                "license": "CC-BY 4.0",
            }
        )
        for target, replacement in [
            ("connection", lambda: self.conn),
            ("upload_path", lambda key: str(Path(self.directory.name) / key)),
            ("describe", self.describe),
            ("banned", lambda: False),
        ]:
            patcher = patch.object(server, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = Flask(__name__)
        self.app.testing = True
        self.app.session_cookie_name = "v2c-session"
        self.app.session_interface = redisession.RedisSessionInterface(self.conn)
        self.app.register_blueprint(server.local_agent, url_prefix="/api/local-agent")

        @self.app.route("/")
        def main():
            return "test"

        @self.app.route("/login")
        def login():
            session["username"] = "Test contributor"
            session["_csrf_token"] = "browser-csrf"
            session["access_token_key"] = "private-oauth-key"
            session["access_token_secret"] = "private-oauth-secret"
            return "ok"

        @self.app.route("/logout")
        def logout():
            session.clear()
            return "ok"

        self.browser = self.app.test_client()
        self.browser.get("/login", base_url="https://localhost")
        self.http = requests.Session()
        self.http.mount("https://localhost/", FlaskTransport(self.app))
        self.addCleanup(self.http.close)

    def browser_post(self, endpoint, **fields):
        return self.browser.post(
            "/api/local-agent/" + endpoint,
            base_url="https://localhost",
            data={"_csrf_token": "browser-csrf", **fields},
        )

    def start(self, **fields):
        response = self.browser_post(
            "start", url=URL, video="true", audio="true", **fields
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.json

    def claim(self, browser_job):
        return agent.post(self.http, "https://localhost", "claim", browser_job["code"])

    def begin(self, job, size=8, metadata=None, extension="webm"):
        return agent.post(
            self.http,
            "https://localhost",
            job["id"] + "/begin",
            job["token"],
            json={
                "size": size,
                "extension": extension,
                "metadata": metadata or self.info,
            },
        )

    def test_agent_to_server_transfer_and_normal_wizard_metadata(self):
        browser_job = self.start()
        job = self.claim(browser_job)
        self.assertNotIn("access_token", json.dumps(job))
        self.assertNotIn("private-oauth", json.dumps(job))
        self.assertNotEqual(browser_job["code"], job["token"])
        path = Path(self.directory.name) / "source.webm"
        path.write_bytes(b"example media data")
        job["chunk_size"] = 5
        agent.transfer(self.http, "https://localhost", job, path, self.info)
        result = self.browser_post("status", id=job["id"]).json
        self.assertEqual(result["state"], "ready")
        metadata = result["metadata"]
        self.assertEqual(metadata["extractor"], "(uploads)")
        self.assertEqual(metadata["queue"], "heavy")
        self.assertFalse(metadata["subtitles"])
        self.assertEqual(metadata["filename"], "Example video")
        uploaded = Path(server.upload_path(metadata["url"].removeprefix("uploads:")))
        self.assertEqual(uploaded.read_bytes(), path.read_bytes())
        info = self.describe.call_args.args[0]
        self.assertEqual(info["webpage_url"], URL)
        self.assertEqual(info["extractor_key"], "Youtube")

    def test_pairing_is_one_use_and_capabilities_are_not_interchangeable(self):
        browser_job = self.start()
        job = self.claim(browser_job)
        with self.assertRaisesRegex(RuntimeError, "already used"):
            self.claim(browser_job)
        with self.assertRaisesRegex(RuntimeError, "agent token"):
            agent.post(
                self.http,
                "https://localhost",
                job["id"] + "/begin",
                browser_job["code"],
                json={},
            )

    def test_auth_csrf_session_ownership_and_logout_revocation(self):
        self.assertEqual(
            self.browser_post("start", url=URL, _csrf_token="wrong").status_code, 403
        )
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post("/api/local-agent/start").status_code, 401)
        browser_job = self.start()
        other = self.app.test_client()
        other.get("/login", base_url="https://localhost")
        denied = other.post(
            "/api/local-agent/status",
            base_url="https://localhost",
            data={
                "id": browser_job["id"],
                "_csrf_token": "browser-csrf",
            },
        )
        self.assertEqual(denied.status_code, 404)
        job = self.claim(browser_job)
        self.browser.get("/logout", base_url="https://localhost")
        with self.assertRaisesRegex(RuntimeError, "session has ended"):
            self.begin(job)

    def test_expired_code_and_replacement_revoke_old_transfer(self):
        browser_job = self.start()
        self.conn.delete(server.pair_key(browser_job["code"]))
        self.assertEqual(
            self.browser_post("status", id=browser_job["id"]).status_code, 410
        )
        job = self.claim(self.start())
        self.begin(job)
        filekey = self.conn.hget(server.job_key(job["id"]), "filekey")
        self.start()
        self.assertFalse(Path(server.upload_path(filekey)).exists())
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.begin(job)

    def test_cancel_deletes_partial_file_but_keeps_ready_file_for_worker(self):
        job = self.claim(self.start())
        self.begin(job)
        key = self.conn.hget(server.job_key(job["id"]), "filekey")
        self.browser_post("cancel", id=job["id"])
        self.assertFalse(Path(server.upload_path(key)).exists())
        job = self.claim(self.start())
        self.begin(job, size=1)
        key = self.conn.hget(server.job_key(job["id"]), "filekey")
        Path(server.upload_path(key)).write_bytes(b"x")
        agent.post(
            self.http, "https://localhost", job["id"] + "/complete", job["token"]
        )
        self.browser_post("cancel", id=job["id"])
        self.assertEqual(Path(server.upload_path(key)).read_bytes(), b"x")

    def test_bad_ranges_incomplete_uploads_and_lost_chunk_response(self):
        job = self.claim(self.start())
        self.begin(job)
        with self.assertRaisesRegex(RuntimeError, "not finished"):
            agent.post(
                self.http, "https://localhost", job["id"] + "/complete", job["token"]
            )
        for content_range, data in [
            ("bytes 0-3/9", b"abcd"),
            ("bytes 0-3/8", b"abc"),
            ("bad", b"abcd"),
        ]:
            with (
                self.subTest(content_range=content_range, data=data),
                self.assertRaises(RuntimeError),
            ):
                agent.post(
                    self.http,
                    "https://localhost",
                    job["id"] + "/chunk",
                    job["token"],
                    data=data,
                    headers={"Content-Range": content_range},
                )
        for _ in range(2):
            result = agent.post(
                self.http,
                "https://localhost",
                job["id"] + "/chunk",
                job["token"],
                data=b"abcd",
                headers={"Content-Range": "bytes 0-3/8"},
            )
            self.assertEqual(result["offset"], 4)
        agent.post(
            self.http,
            "https://localhost",
            job["id"] + "/chunk",
            job["token"],
            data=b"efgh",
            headers={"Content-Range": "bytes 4-7/8"},
        )
        agent.post(
            self.http, "https://localhost", job["id"] + "/complete", job["token"]
        )
        agent.post(
            self.http, "https://localhost", job["id"] + "/complete", job["token"]
        )

    def test_invalid_media_metadata_sizes_and_extensions_are_rejected(self):
        job = self.claim(self.start())
        cases = [
            {"metadata": {**self.info, "id": "wrongwrong1"}},
            {"metadata": {**self.info, "license": "Standard YouTube License"}},
            {
                "metadata": {
                    **self.info,
                    "license": "",
                    "description": "Creative Commons",
                }
            },
            {"metadata": {**self.info, "height": "large"}},
            {"size": server.MAX_SIZE + 1},
            {"size": 0},
            {"size": -1},
            {"extension": "html"},
            {"extension": "../x"},
            {"extension": []},
        ]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(RuntimeError):
                self.begin(job, **fields)
        self.assertEqual(
            self.conn.hget(server.job_key(job["id"]), "state"), "downloading"
        )

    def test_reported_agent_error_reaches_browser(self):
        job = self.claim(self.start())
        agent.post(
            self.http,
            "https://localhost",
            job["id"] + "/error",
            job["token"],
            json={"error": "Sign in to confirm you're not a bot"},
        )
        status = self.browser_post("status", id=job["id"]).json
        self.assertEqual(status["state"], "error")
        self.assertIn("not a bot", status["error"])

    def test_only_canonical_individual_youtube_links_are_accepted(self):
        with self.app.test_request_context():
            for value in [
                URL,
                "https://youtu.be/abcdefghijk?t=1",
                "https://m.youtube.com/shorts/abcdefghijk",
                "https://www.youtube-nocookie.com/embed/abcdefghijk",
            ]:
                self.assertEqual(server.youtube_url(value), URL)
            for value in [
                "https://youtube.com.evil.test/watch?v=abcdefghijk",
                "https://youtube.com/playlist?list=abc",
                "file:///watch?v=abcdefghijk",
                "https://user@youtube.com/watch?v=abcdefghijk",
            ]:
                with self.subTest(value=value), self.assertRaises(HTTPException):
                    server.youtube_url(value)

    def test_agent_rejects_untrusted_servers_and_redirects(self):
        code = "a" * 43
        self.assertEqual(
            agent.parse_pairing("https://video2commons.toolforge.org/#" + code)[1], code
        )
        for host in [
            "http://video2commons.toolforge.org",
            "https://evil.test",
            "https://video2commons.toolforge.org.evil.test",
            "https://user@video2commons.toolforge.org",
            "https://video2commons.toolforge.org/path",
        ]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                agent.parse_pairing(host + "#" + code)
        http = Mock()
        http.post.return_value = Mock(ok=False, status_code=302)
        http.post.return_value.json.side_effect = ValueError()
        with self.assertRaises(RuntimeError):
            agent.post(http, "https://video2commons.toolforge.org", "claim", code)
        self.assertFalse(http.post.call_args.kwargs["allow_redirects"])

    def test_agent_does_not_download_non_cc_or_live_video(self):
        for info in [
            {**self.info, "license": "Standard YouTube License"},
            {**self.info, "is_live": True},
            {**self.info, "id": "wrongwrong1"},
        ]:
            with self.subTest(info=info), self.assertRaises(ValueError):
                agent.check_info(info, "abcdefghijk")

    def test_uploader_links_are_safe_for_wikitext_and_remote_urls_are_ignored(self):
        with self.app.test_request_context():
            info = server.clean_metadata(
                {
                    "metadata": {
                        **self.info,
                        "uploader_url": "https://youtube.com/@author]{{bad}}?x=y",
                        "url": "http://internal.test/private",
                        "formats": [{"url": "http://internal.test"}],
                    }
                },
                URL,
            )
            self.assertNotIn("]", info["uploader_url"])
            self.assertNotIn("{", info["uploader_url"])
            self.assertNotIn("?", info["uploader_url"])
            self.assertNotIn("internal.test", json.dumps(info))
            self.assertEqual(info["webpage_url"], URL)

    def test_agent_downloads_locally_only_after_checking_the_license(self):
        job = {"url": URL, "video": True, "audio": True, "max_size": server.MAX_SIZE}
        dl = Mock()
        dl.extract_info.return_value = self.info
        dl.process_ie_result.side_effect = lambda *args, **kwargs: (
            Path(self.directory.name) / "media.mkv"
        ).write_bytes(b"media")
        with (
            patch.object(agent.shutil, "which", return_value="ffmpeg"),
            patch.object(agent.yt_dlp, "YoutubeDL") as factory,
        ):
            factory.return_value.__enter__.return_value = dl
            path, metadata = agent.download(job, self.directory.name)
            self.assertEqual(path.read_bytes(), b"media")
            self.assertEqual(metadata["license"], server.CC_LICENSE)
            dl.extract_info.assert_called_once_with(URL, download=False)
            dl.process_ie_result.assert_called_once_with(self.info, download=True)
            self.assertTrue(factory.call_args.args[0]["noplaylist"])
            dl.reset_mock()
            dl.extract_info.return_value = {
                **self.info,
                "license": "Standard YouTube License",
            }
            with self.assertRaises(ValueError):
                agent.download(job, self.directory.name)
            dl.process_ie_result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
