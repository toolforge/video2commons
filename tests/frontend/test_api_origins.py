"""Tests for the API used by a page of another site, with a token from /connect.

A user script on Commons, e.g. a batch uploader, cannot use the cookie of
video2commons: it opens /connect in a popup, the user allows it, and the page
gets a token that it sends in the Authorization header. The API lets the pages
of the sites in api_origins read its answers, and takes the edit summary of the
tool for the uploads it starts.
"""

import importlib
import io
import json
import pathlib
import re
from urllib.parse import parse_qs, urlparse

import flask
import jinja2
import pytest

from tests.frontend.conftest import FakeRedis
from video2commons import config
from video2commons.frontend import api, i18n, upload
from video2commons.frontend.app import app

# The module, which the Flask app of the same name hides in the package.
app_module = importlib.import_module("video2commons.frontend.app")

COMMONS = "https://commons.wikimedia.org"
OTHER = "https://example.org"
SUMMARY = "Batch upload using [[User:Example/tool.js|tool]]"
TASK = {
    "url": "uploads:00000000-0000-1000-8000-000000000000.mov",
    "extractor": "",
    "subtitles": "false",
    "filename": "Example video",
    "filedesc": "== Summary ==",
    "format": "webm (AV1/Opus)",
}


@pytest.fixture(autouse=True)
def login_check(monkeypatch):
    """The login check of the API, which is off when session_key is not set."""
    monkeypatch.setattr(api, "session_key", "internal")


class TtlRedis(FakeRedis):
    """FakeRedis that also keeps the time to live of each key, in seconds."""

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.ttl = {}

    def setex(self, key, ttl, value):
        super().setex(key, ttl, value)
        self.ttl[key] = ttl

    def expire(self, key, ttl):
        if key in self.data:
            self.ttl[key] = ttl


@pytest.fixture
def redis(client, monkeypatch):
    """The fake Redis of the sessions, which holds the session of the client."""
    redis = TtlRedis(app.session_interface.redis.data)
    monkeypatch.setattr(app.session_interface, "redis", redis)
    return redis


@pytest.fixture
def pages(monkeypatch):
    """The pages that the frontend renders, and a login that always works."""
    rendered = []

    def render_template(name, **context):
        rendered.append((name, context))
        return name

    monkeypatch.setattr(app_module, "render_template", render_template)
    monkeypatch.setattr(app_module, "dologin", lambda: None)
    return rendered


def tokens(redis):
    """The API tokens in Redis, and the session that each one opens."""
    prefix = "apitoken:"
    return {k[len(prefix) :]: v for k, v in redis.data.items() if k.startswith(prefix)}


def session_id(redis):
    """The ID of the only session in Redis."""
    (key,) = [key for key in redis.data if key.startswith("session:")]
    return key[len("session:") :]


def allow(client, pages):
    """Allow COMMONS on /connect, as the user does, and get the token."""
    response = client.post("/connect", data={"origin": COMMONS, "_csrf_token": "csrf"})
    assert response.status_code == 200
    name, context = pages[-1]
    assert name == "connect.min.html"
    return context["token"]


def from_commons(token=None, **headers):
    """The headers of a call to the API from a page of Commons."""
    if token:
        headers["Authorization"] = "Bearer " + token
    return {"Origin": COMMONS, **headers}


class TestConnect:
    def test_asks_the_user_first(self, client, pages, redis):
        response = client.get("/connect", query_string={"origin": COMMONS})

        assert response.status_code == 200
        assert pages == [
            (
                "connect.min.html",
                {
                    "origin": COMMONS,
                    "username": "Example user",
                    "loggedin": True,
                    "csrf": "csrf",
                },
            )
        ]
        assert tokens(redis) == {}

    def test_gives_a_token_that_opens_the_session(self, client, pages, redis):
        token = allow(client, pages)

        assert tokens(redis) == {token: session_id(redis)}
        assert pages[-1][1]["origin"] == COMMONS
        assert len(token) >= 40

    def test_keeps_its_page_out_of_frames_and_caches(self, client, pages):
        for response in (
            client.get("/connect", query_string={"origin": COMMONS}),
            client.post("/connect", data={"origin": COMMONS, "_csrf_token": "csrf"}),
        ):
            assert response.headers["X-Frame-Options"] == "DENY"
            assert response.headers["Content-Security-Policy"] == (
                "frame-ancestors 'none'"
            )
            assert response.headers["Cache-Control"] == "no-store"

    @pytest.mark.parametrize("csrf", [None, "", "wrong"])
    def test_gives_no_token_without_the_csrf_token(self, client, pages, redis, csrf):
        data = {"origin": COMMONS}
        if csrf is not None:
            data["_csrf_token"] = csrf

        response = client.post("/connect", data=data)

        assert response.status_code == 400
        assert pages[-1][0] == "error.min.html"
        assert tokens(redis) == {}

    @pytest.mark.parametrize(
        "origin", ["", OTHER, "http://commons.wikimedia.org", COMMONS + ".example.org"]
    )
    def test_refuses_the_other_origins(self, client, pages, redis, origin):
        asked = client.get("/connect", query_string={"origin": origin})
        allowed = client.post(
            "/connect", data={"origin": origin, "_csrf_token": "csrf"}
        )

        assert asked.status_code == allowed.status_code == 400
        assert [name for name, context in pages] == ["error.min.html"] * 2
        assert tokens(redis) == {}

    def test_logs_the_user_in_first(self, client):
        response = app.test_client().get("/connect", query_string={"origin": COMMONS})

        assert response.status_code == 302
        location = urlparse(response.headers["Location"])
        assert location.path == "/oauthinit"
        (returnto,) = parse_qs(location.query)["returnto"]
        assert urlparse(returnto).path == "/connect"
        assert parse_qs(urlparse(returnto).query) == {"origin": [COMMONS]}


class TestToken:
    def test_opens_the_session_without_a_cookie(self, client, pages, redis):
        token = allow(client, pages)

        response = app.test_client().get("/api/csrf", headers=from_commons(token))

        assert response.get_json() == {"csrf": "csrf"}
        assert "Set-Cookie" not in response.headers

    def test_that_opens_nothing_is_not_logged_in(self, client, redis):
        before = dict(redis.data)

        response = app.test_client().get("/api/csrf", headers=from_commons("nothing"))

        assert response.get_json()["error"] == "Are you logged in?"
        assert "Set-Cookie" not in response.headers
        assert redis.data == before

    def test_is_not_rescued_by_the_cookie(self, client):
        response = client.get("/api/csrf", headers=from_commons("nothing"))

        assert response.get_json()["error"] == "Are you logged in?"

    def test_opens_nothing_once_the_user_logs_out(self, client, pages, redis):
        token = allow(client, pages)

        client.get("/logout")
        response = app.test_client().get("/api/csrf", headers=from_commons(token))

        assert response.get_json()["error"] == "Are you logged in?"

    @pytest.mark.parametrize(
        ("path", "header", "expected"),
        [
            ("/api/csrf", "Bearer abc", "abc"),
            ("/api/csrf", "bearer  abc ", "abc"),
            ("/api/csrf", "Basic abc", None),
            ("/api/csrf", "Bearer", None),
            ("/connect", "Bearer abc", None),
            ("/", "Bearer abc", None),
        ],
    )
    def test_is_only_read_by_the_api(self, redis, path, header, expected):
        with app.test_request_context(path, headers={"Authorization": header}):
            assert app.session_interface.bearer_token(flask.request) == expected


class TestTokenLifetime:
    DAY = 24 * 3600

    def test_lasts_as_long_as_the_session(self, client, pages, redis):
        token = allow(client, pages)

        assert redis.ttl["apitoken:" + token] == self.DAY

    def test_is_renewed_with_the_session_when_it_is_used(self, client, pages, redis):
        token = allow(client, pages)
        sid = session_id(redis)
        # A day later, almost.
        redis.ttl["apitoken:" + token] = redis.ttl["session:" + sid] = 1

        app.test_client().get("/api/csrf", headers=from_commons(token))

        assert redis.ttl["apitoken:" + token] == self.DAY
        assert redis.ttl["session:" + sid] == self.DAY

    def test_keeps_what_the_session_learns_through_it(self, client, pages, redis):
        token = allow(client, pages)
        sid = session_id(redis)
        stored = json.loads(redis.data["session:" + sid])
        del stored["_csrf_token"]
        redis.data["session:" + sid] = json.dumps(stored)

        csrf = app.test_client().get("/api/csrf", headers=from_commons(token))

        new = csrf.get_json()["csrf"]
        assert json.loads(redis.data["session:" + sid])["_csrf_token"] == new


class TestCors:
    def test_answers_are_readable_by_the_allowed_origins(self, client):
        response = client.get("/api/csrf", headers=from_commons())

        assert response.headers["Access-Control-Allow-Origin"] == COMMONS
        assert "Origin" in response.headers["Vary"]
        # The answers to a request with the cookie stay unreadable.
        assert "Access-Control-Allow-Credentials" not in response.headers

    def test_answers_are_not_readable_by_other_origins(self, client):
        response = client.get("/api/csrf", headers={"Origin": OTHER})

        assert "Access-Control-Allow-Origin" not in response.headers
        assert "Origin" in response.headers["Vary"]

    def test_errors_are_readable_too(self, redis):
        response = app.test_client().get("/api/csrf", headers=from_commons())

        assert response.get_json()["error"] == "Are you logged in?"
        assert response.headers["Access-Control-Allow-Origin"] == COMMONS

    def test_errors_of_the_views_are_readable_too(self, client, pages, redis):
        token = allow(client, pages)

        response = app.test_client().post(
            "/api/task/run", data={"_csrf_token": "csrf"}, headers=from_commons(token)
        )

        assert response.get_json()["step"] == "error"
        assert "KeyError" in response.get_json()["error"]
        assert response.headers["Access-Control-Allow-Origin"] == COMMONS

    def test_the_preflight_needs_no_login(self, redis):
        response = app.test_client().options(
            "/api/upload/upload",
            headers=from_commons(
                **{
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-range",
                }
            ),
        )

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == COMMONS
        assert response.headers["Access-Control-Allow-Methods"] == "GET, POST"
        assert response.headers["Access-Control-Allow-Headers"] == (
            "Authorization, Content-Range"
        )
        assert not response.get_data()


class FakeTaskRedis:
    """The Redis commands of the tasks of the API, in memory."""

    def __init__(self):
        self.data = {}
        self.ttl = {}

    def lpush(self, key, value):
        self.data.setdefault(key, []).insert(0, value)

    def lrange(self, key, start, end):
        return list(self.data.get(key, []))

    def lrem(self, key, count, value):
        self.data[key] = [item for item in self.data.get(key, []) if item != value]

    def expire(self, key, ttl):
        if key in self.data:
            self.ttl[key] = ttl

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)


class Started(list):
    """What each task started got, and the fake Redis of the tasks."""

    redis = None


@pytest.fixture
def started(client, monkeypatch):
    """The tasks the API starts, which nothing runs.

    For each one: its arguments, its queue, its ID, and the summary that was
    in Redis when it was queued.
    """
    calls = Started()
    calls.redis = FakeTaskRedis()

    class Result:
        def __init__(self, task_id):
            self.id = task_id

    def apply_async(args, queue, task_id):
        comment = calls.redis.get("comment:" + task_id)
        calls.append(
            {"args": list(args), "queue": queue, "id": task_id, "comment": comment}
        )
        return Result(task_id)

    monkeypatch.setattr(api.worker.main, "apply_async", apply_async)
    monkeypatch.setattr(api, "redisconnection", calls.redis)
    monkeypatch.setattr(api.stats, "increment_queue_counter", lambda conn: None)
    monkeypatch.setattr(api, "publish_notification", lambda *args: None)
    monkeypatch.setattr(api, "get_task_status", lambda *args: {})
    with client.session_transaction() as session:
        session["access_token_key"] = "access-token"
        session["access_token_secret"] = "access-secret"
    return calls


class TestSummary:
    def test_is_kept_beside_the_task_before_it_is_queued(self, api_post, started):
        answer = api_post("task/run", comment=f"  {SUMMARY} ", **TASK)

        (task,) = started
        assert answer == {"id": task["id"], "step": "success"}
        assert task["comment"] == SUMMARY
        assert started.redis.ttl["comment:" + task["id"]] == 14 * 24 * 3600

    def test_leaves_the_parameters_as_an_older_worker_reads_them(
        self, api_post, started
    ):
        api_post("task/run", comment=SUMMARY, **TASK)
        api_post("task/run", **TASK)

        assert [len(task["args"]) for task in started] == [9, 9]
        assert started[1]["comment"] is None

    @pytest.mark.parametrize(
        ("comment", "kept"),
        [
            ("   ", None),
            ("Batch\nupload  using\ttool", "Batch upload using tool"),
            ("x" * 600, "x" * 500),
        ],
    )
    def test_is_one_line_that_fits(self, api_post, started, comment, kept):
        api_post("task/run", comment=comment, **TASK)

        assert started[-1]["comment"] == kept

    def test_goes_with_the_task_when_it_is_restarted(self, api_post, started):
        api_post("task/run", comment=SUMMARY, **TASK)
        first = started[-1]["id"]

        assert api_post("task/restart", id=first)["restart"] == "success"

        assert started[-1]["id"] != first
        assert started[-1]["comment"] == SUMMARY
        assert started[-1]["queue"] == api.HEAVY_QUEUE

    def test_goes_when_the_task_is_removed(self, api_post, started):
        api_post("task/run", comment=SUMMARY, **TASK)
        task = started[-1]["id"]

        assert api_post("task/remove", id=task)["remove"] == "success"

        assert "comment:" + task not in started.redis.data


class TestWhatATokenMayDo:
    def test_sends_a_file(self, client, pages, redis, monkeypatch, tmp_path):
        monkeypatch.setattr(upload, "getpath", lambda key: str(tmp_path / key))
        token = allow(client, pages)

        response = app.test_client().post(
            "/api/upload/upload",
            data={"_csrf_token": "csrf", "file": (io.BytesIO(b"hello"), "clip.mov")},
            headers=from_commons(token, **{"Content-Range": "bytes 0-4/5"}),
        )

        answer = response.get_json()
        assert answer["result"] == "Success"
        assert answer["filekey"].endswith(".mov")
        assert (tmp_path / answer["filekey"]).read_bytes() == b"hello"
        assert response.headers["Access-Control-Allow-Origin"] == COMMONS

    def test_never_acts_as_a_maintainer(self, client, pages, redis, api_post, started):
        with client.session_transaction() as session:
            session["is_maintainer"] = True
        token = allow(client, pages)

        # The cookie of a maintainer removes the task of somebody else...
        assert api_post("task/remove", id="their-task")["remove"] == "success"
        # ...and the token of the same session does not.
        response = app.test_client().post(
            "/api/task/remove",
            data={"_csrf_token": "csrf", "id": "their-task"},
            headers=from_commons(token),
        )
        assert response.get_json()["error"] == "Task must belong to you."


class TestOrigins:
    @pytest.mark.parametrize(
        ("value", "origins"),
        [
            ([COMMONS], {COMMONS}),
            (COMMONS + "/", {COMMONS}),
            (
                ["HTTPS://Commons.Wikimedia.org", "http://localhost:5002"],
                {COMMONS, "http://localhost:5002"},
            ),
            (["*"], set()),
            (["null"], set()),
            ([COMMONS + "/wiki/Main_Page"], set()),
            (["http://commons.wikimedia.org"], set()),
            ([None, 1, ""], set()),
            (None, set()),
            ({COMMONS: True}, set()),
        ],
    )
    def test_are_origins_and_nothing_else(self, value, origins):
        assert config.parse_api_origins(value) == frozenset(origins)

    def test_a_string_is_one_origin_and_not_letters(self):
        origins = config.parse_api_origins(COMMONS)

        assert "https://commons.wiki" not in origins
        assert None not in origins


class TestCorsOfEveryApiUrl:
    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/api/task/run"), ("GET", "/api/nope"), ("POST", "/api/nope")],
    )
    def test_that_does_not_exist_is_readable_too(self, redis, pages, method, path):
        response = app.test_client().open(path, method=method, headers=from_commons())

        assert response.headers["Access-Control-Allow-Origin"] == COMMONS

    def test_but_not_the_other_pages(self, client, pages):
        response = client.get(
            "/connect", query_string={"origin": COMMONS}, headers=from_commons()
        )

        assert "Access-Control-Allow-Origin" not in response.headers
        assert "Origin" not in response.headers.get("Vary", "")


TEMPLATES = pathlib.Path(app_module.__file__).parent / "templates"
HOSTILE_NAME = 'Example "user" </script>'


@pytest.fixture
def render(monkeypatch):
    """Render a template from its source, in English.

    The pages are served minified by gulp build, which the tests do not run:
    each template is read from its source instead, which only differs from
    it in whitespace.
    """
    english = json.loads((TEMPLATES.parent / "i18n" / "en.json").read_text())
    monkeypatch.setattr(i18n, "get", lambda lang: english)
    sources = jinja2.FunctionLoader(
        lambda name: (TEMPLATES / name.replace(".min.html", ".html")).read_text()
    )
    environment = app.jinja_env.overlay(loader=sources)

    def render(name, **context):
        with app.test_request_context("/connect"):
            return environment.get_template(name).render(loggedin=True, **context)

    return render


class TestConnectPage:
    def test_asks_with_the_origin_and_the_csrf_token(self, render):
        html = render(
            "connect.min.html", origin=COMMONS, username=HOSTILE_NAME, csrf="the-csrf"
        )

        assert '<form id="connect-form" method="post" action="/connect">' in html
        assert f'<input type="hidden" name="origin" value="{COMMONS}">' in html
        assert '<input type="hidden" name="_csrf_token" value="the-csrf">' in html
        # Opened without the window that asked, it gives nothing to allow.
        assert re.search(
            r'if \(!window\.opener\) \{\s*document\.getElementById\("connect-form"\)'
            r"\.hidden = true;",
            html,
        )
        assert (
            f"{COMMONS} asks to use video2commons as "
            "Example &#34;user&#34; &lt;/script&gt;: to send it files"
        ) in html
        assert "postMessage" not in html

    def test_gives_the_token_to_the_origin_only(self, render):
        html = render(
            "connect.min.html", origin=COMMONS, username=HOSTILE_NAME, token="T0k-en_x"
        )

        call = re.search(r"window\.opener\.postMessage\((.*?)\);", html, re.DOTALL)
        assert call, "the token is posted to the window that opened the popup"
        assert re.fullmatch(
            r'\s*\{\s*type: "video2commons-token",\s*token: "T0k-en_x",'
            r'\s*username: "Example \\"user\\" \\u003c/script\\u003e"\s*\},'
            r'\s*"https://commons\.wikimedia\.org"\s*',
            call.group(1),
        ), call.group(1)
        assert html.count("T0k-en_x") == 1
        assert "window.close()" in html
