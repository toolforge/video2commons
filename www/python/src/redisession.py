#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Source: http://flask.pocoo.org/snippets/75/ under Public Domain
#
import pickle
from datetime import timedelta
from uuid import uuid4
from redis import Redis
from flask.sessions import SessionInterface, SessionMixin


class RedisSession(dict, SessionMixin):
    def __init__(self, initial=None, sid=None, new=False):
        self.sid = sid
        self.new = new
        self.modified = False
        if initial:
            self.update(initial)

    def on_update(self):
        self.modified = True

    def __setitem__(self, key, val):
        self.on_update()
        return dict.__setitem__(self, key, val)

    def __delitem__(self, key):
        self.on_update()
        return self.dict.__delitem__(self, key)

    def clear(self):
        self.on_update()
        return self.dict.clear(self)


class RedisSessionInterface(SessionInterface):
    serializer = pickle
    session_class = RedisSession

    def __init__(self, redis=None, prefix='session:'):
        if redis is None:
            redis = Redis()
        self.redis = redis
        self.prefix = prefix

    def generate_sid(self):
        return str(uuid4())

    def get_redis_expiration_time(self, app, session):
        if session.permanent:
            return app.permanent_session_lifetime
        return timedelta(days=1)

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)
        if not sid:
            sid = self.generate_sid()
            return self.session_class(sid=sid, new=True)
        val = self.redis.get(self.prefix + sid)
        if val is not None:
            data = self.serializer.loads(val)
            return self.session_class(data, sid=sid)
        return self.session_class(sid=sid, new=True)

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        path = '/video2commons/'

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
                                domain=domain, path=path)
