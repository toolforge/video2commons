# -*- coding: UTF-8 -*-
#
# Adapted from: http://flask.pocoo.org/snippets/75/ under Public Domain
#

"""Server side session on Redis."""

import json
import secrets
from datetime import timedelta
from uuid import uuid4

from flask import url_for
from flask.sessions import SessionInterface, SessionMixin
from redis import Redis


class RedisSession(dict, SessionMixin):
    """Redis Session class."""

    def __init__(self, initial=None, sid=None, new=False, token=None):
        """Initialize the instance."""
        self.sid = sid
        self.new = new
        # The API token the session was opened with, by a page of another
        # site. Such a session never gets a cookie.
        self.token = token
        initial = initial or {}
        if initial:
            self.update(initial or {})

        self._initials = json.dumps(dict(self))

    @property
    def modified(self):
        """Check if this is modified recursively."""
        return json.dumps(dict(self)) != self._initials

    def rollback(self):
        """Rollback all changes."""
        self.clear()
        self.update(json.loads(self._initials))


class RedisSessionInterface(SessionInterface):
    """Redis Session interface: provides methods dealing with sessions."""

    serializer = json
    session_class = RedisSession

    def __init__(
        self,
        redis=None,
        prefix="session:",
        token_prefix="apitoken:",
        token_path="/api/",
        token_lifetime=timedelta(days=1),
    ):
        """Initialize the instance."""
        if redis is None:
            redis = Redis()
        self.redis = redis
        self.prefix = prefix
        self.token_prefix = token_prefix
        # Only the requests to the API may be authenticated with a token.
        self.token_path = token_path
        self.token_lifetime = token_lifetime

    def generate_sid(self):
        """Generate a session ID."""
        return str(uuid4())

    def get_redis_expiration_time(self, app, session):
        """Get Redis expiration time."""
        if session.permanent:
            return app.permanent_session_lifetime
        return timedelta(days=1)

    def issue_token(self, session):
        """Create an API token that opens this session.

        The token lasts a day from now however much it is used, so one that
        leaks stops working by itself. Logging out ends it sooner, since it
        deletes the session that the token opens.
        """
        token = secrets.token_urlsafe(32)
        self.redis.setex(
            self.token_prefix + token,
            int(self.token_lifetime.total_seconds()),
            session.sid,
        )
        return token

    def bearer_token(self, request):
        """Get the API token of a request to the API, if it has one."""
        if not request.path.startswith(self.token_path):
            return None
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None
        return token

    def load_session(self, sid, token=None):
        """Get the session with this ID from Redis, or None."""
        val = self.redis.get(self.prefix + sid)
        if val is None:
            return None
        try:
            data = self.serializer.loads(val)
        except ValueError:
            return None
        return self.session_class(data, sid=sid, token=token)

    def open_session(self, app, request):
        """Get session from Redis / start a new session."""
        token = self.bearer_token(request)
        if token is not None:
            # The token of a page of another site, which the browser sends no
            # cookie of ours to. The cookie is not looked at either, so that it
            # cannot stand in for a token that opens nothing.
            sid = self.redis.get(self.token_prefix + token)
            session = self.load_session(sid, token=token) if sid else None
            if session is not None:
                return session
            return self.session_class(sid=self.generate_sid(), new=True, token=token)

        sid = request.cookies.get(app.session_cookie_name)
        if sid:
            session = self.load_session(sid)
            if session is not None:
                return session

        # SECURITY: If the session id is invalid, we create a new one, to
        # prevent cookie-injection.
        # https://www.usenix.org/system/files/conference/usenixsecurity15/sec15-paper-zheng.pdf
        sid = self.generate_sid()
        return self.session_class(sid=sid, new=True)

    def save_session(self, app, session, response):
        """Save session to Redis."""
        if session is None:
            return
        if session.token is not None:
            self.save_token_session(app, session)
            return

        domain = self.get_cookie_domain(app)
        path = url_for("main", _external=False)

        if not session:
            self.redis.delete(self.prefix + session.sid)
            if session.modified:
                response.delete_cookie(
                    app.session_cookie_name, domain=domain, path=path
                )
        else:
            redis_exp = self.get_redis_expiration_time(app, session)
            cookie_exp = self.get_expiration_time(app, session)
            if session.modified:
                val = self.serializer.dumps(dict(session))
                self.redis.setex(
                    self.prefix + session.sid, int(redis_exp.total_seconds()), val
                )
            else:
                self.redis.expire(
                    self.prefix + session.sid, int(redis_exp.total_seconds())
                )
            response.set_cookie(
                app.session_cookie_name,
                session.sid,
                expires=cookie_exp,
                httponly=True,
                domain=domain,
                path=path,
                secure=True,
            )

    def save_token_session(self, app, session):
        """Save a session opened with a token, without a cookie."""
        if session.new:
            # The token opened no session: there is nothing to keep, and a
            # session made for it would only be a key nobody can use.
            return
        if not session:
            self.redis.delete(self.prefix + session.sid)
            return
        redis_exp = int(self.get_redis_expiration_time(app, session).total_seconds())
        if session.modified:
            self.redis.setex(
                self.prefix + session.sid,
                redis_exp,
                self.serializer.dumps(dict(session)),
            )
        else:
            self.redis.expire(self.prefix + session.sid, redis_exp)
        # The session goes on while a tool uses it, as it does on the page of
        # video2commons, but the token is not renewed with it: it ends when
        # issue_token said, and the tool asks the user for a new one.

    def abandon_session(self, app, session):
        """Delete the session from redis, empty it, and reinit."""
        session.clear()

        if not session.new:
            self.redis.delete(self.prefix + session.sid)

            sid = self.generate_sid()
            session._get_current_object().__init__(sid=sid, new=True)
