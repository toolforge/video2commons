#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Adapted from: http://flask.pocoo.org/snippets/75/ under Public Domain
#

"""Server side session on Redis."""

import json
from datetime import timedelta
from uuid import uuid4
from redis import Redis
from flask import url_for
from flask.sessions import SessionInterface, SessionMixin


class RedisSession(dict, SessionMixin):
    """Redis Session class."""

    def __init__(self, initial=None, sid=None, new=False):
        """Initialize the instance."""
        self.sid = sid
        self.new = new
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

    def __init__(self, redis=None, prefix='session:'):
        """Initialize the instance."""
        if redis is None:
            redis = Redis()
        self.redis = redis
        self.prefix = prefix

    def generate_sid(self):
        """Generate a session ID."""
        return str(uuid4())

    def get_redis_expiration_time(self, app, session):
        """Get Redis expiration time."""
        if session.permanent:
            return app.permanent_session_lifetime
        return timedelta(days=1)

    def open_session(self, app, request):
        """Get session from Redis / start a new session."""
        sid = request.cookies.get(app.session_cookie_name)
        if sid:
            val = self.redis.get(self.prefix + sid)
            if val is not None:
                try:
                    data = self.serializer.loads(val)
                except ValueError:
                    pass
                else:
                    return self.session_class(data, sid=sid)

        # SECURITY: If the session id is invalid, we create a new one, to
        # prevent cookie-injection.
        # https://www.usenix.org/system/files/conference/usenixsecurity15/sec15-paper-zheng.pdf
        sid = self.generate_sid()
        return self.session_class(sid=sid, new=True)

    def save_session(self, app, session, response):
        """Save session to Redis."""
        domain = self.get_cookie_domain(app)
        path = url_for('main', _external=False)

        if not session:
            self.redis.delete(self.prefix + session.sid)
            if session.modified:
                response.delete_cookie(app.session_cookie_name,
                                       domain=domain, path=path)
        else:
            redis_exp = self.get_redis_expiration_time(app, session)
            cookie_exp = self.get_expiration_time(app, session)
            if session.modified:
                val = self.serializer.dumps(dict(session))
                self.redis.setex(self.prefix + session.sid, val,
                                 int(redis_exp.total_seconds()))
            else:
                self.redis.expire(self.prefix + session.sid,
                                  int(redis_exp.total_seconds()))
            response.set_cookie(app.session_cookie_name, session.sid,
                                expires=cookie_exp, httponly=True,
                                domain=domain, path=path, secure=True)

    def abandon_session(self, app, session):
        """Delete the session from redis, empty it, and reinit."""
        session.clear()

        if not session.new:
            self.redis.delete(self.prefix + session.sid)

            sid = self.generate_sid()
            session.__init__(sid=sid, new=True)
