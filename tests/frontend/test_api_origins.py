"""Tests for the API used by a page of another site, with a token from /connect.

A user script on Commons, e.g. a batch uploader, cannot use the cookie of
video2commons: it opens /connect in a popup, the user allows it, and the page
gets a token that it sends in the Authorization header. The API lets the pages
of the sites in api_origins read its answers, and takes the edit summary of the
tool for the uploads it starts.
"""

import importlib
import json
from urllib.parse import parse_qs, urlparse

import flask
import pytest

from video2commons.frontend import api
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


@pytest.fixture
def redis(client):
    """The fake Redis of the sessions, which holds the session of the client."""
    return app.session_interface.redis


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
    """The Redis commands of starting a task, in memory."""

    def __init__(self):
        self.data = {}

    def lpush(self, key, value):
        self.data.setdefault(key, []).insert(0, value)

    def expire(self, key, ttl):
        pass

    def set(self, key, value):
        self.data[key] = value


class Started(list):
    """The parameters of each task started, and the fake Redis they went to."""

    redis = None


@pytest.fixture
def started(client, monkeypatch):
    """The parameters of the tasks the API starts, which nothing runs."""
    calls = Started()

    class Result:
        id = "task-id"

    def apply_async(args, queue):
        calls.append(list(args))
        return Result()

    task_redis = FakeTaskRedis()
    monkeypatch.setattr(api.worker.main, "apply_async", apply_async)
    monkeypatch.setattr(api, "redisconnection", task_redis)
    monkeypatch.setattr(api.stats, "increment_queue_counter", lambda conn: None)
    monkeypatch.setattr(api, "publish_notification", lambda *args: None)
    monkeypatch.setattr(api, "get_task_status", lambda *args: {})
    with client.session_transaction() as session:
        session["access_token_key"] = "access-token"
        session["access_token_secret"] = "access-secret"
    calls.redis = task_redis
    return calls


class TestSummary:
    def test_a_task_takes_the_summary_of_the_tool(self, api_post, started):
        assert api_post("task/run", comment=f"  {SUMMARY} ", **TASK) == {
            "id": "task-id",
            "step": "success",
        }

        assert started[-1][-1] == SUMMARY
        # And keeps it when it is restarted, from the parameters it kept.
        assert json.loads(started.redis.data["params:task-id"])[-1] == SUMMARY

    def test_a_task_without_one_keeps_the_nine_parameters(self, api_post, started):
        api_post("task/run", **TASK)
        api_post("task/run", comment="   ", **TASK)

        assert [len(params) for params in started] == [9, 9]

    def test_a_summary_is_cut_to_what_mediawiki_keeps(self, api_post, started):
        api_post("task/run", comment="x" * 600, **TASK)

        assert started[-1][-1] == "x" * api.COMMENT_MAX_LENGTH
