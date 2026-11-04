"""Call the API of the frontend as a user who is logged in."""

import pytest

from video2commons.frontend.app import app


class FakeRedis:
    """The Redis commands of the sessions of the frontend, in memory."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value

    def expire(self, key, ttl):
        pass

    def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def client(monkeypatch):
    """A test client of a user who is logged in, with their CSRF token."""
    monkeypatch.setattr(app.session_interface, "redis", FakeRedis())
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "Example user"
        session["_csrf_token"] = "csrf"
    return client


@pytest.fixture
def api_post(client):
    """POST to an endpoint of the API with the CSRF token, and get its JSON."""

    def post(endpoint, **data):
        response = client.post("/api/" + endpoint, data={"_csrf_token": "csrf", **data})
        assert response.status_code == 200
        return response.get_json()

    return post
