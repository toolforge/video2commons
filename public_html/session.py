#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2015 Zhuyifei1999
#
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

import os
from Cookie import SimpleCookie
from redis import Redis
from config import redis_key, session_expire

class Session(object):
    def __init__(self):
        self.redis = Redis(host="tools-redis")
        self.key = redis_key
        self.cookie = Cookie.SimpleCookie()
        self.id = get_id_from_cookie()
        if not self.id: self.generate_id()
        self.redis.expire(self.get_key(), session_expire*2)

    def get_key(self):
        return self.key + ":" + self.id

    def get_id_from_cookie(self):
        cookiestr = os.environ.get('HTTP_COOKIE')
        if not cookiestr: return
        self.cookie.load(cookiestr)
        if not 'session' in self.cookie: return
        return self.cookie['session'].value

    def generate_id(self):
        for i in range(10): # 10 tries
            self.id = os.urandom(16).encode('hex')
            if self.redis.exists(self.get_key()): continue
        else:
            raise RuntimeError("Too many retries to generate a session key")

    def as_cookie(self):
        self.cookie['session'] = self.id
        self.cookie['session']['expires'] = session_expire
        self.cookie['session']['domian'] = "tools.wmflabs.org"
        self.cookie['session']['path'] = "/video2commons/"
        self.cookie['session']['httponly'] = True
        return self.cookie

    def __len__(self):
        return self.redis.hlen(self.get_key())

    def __getitem__(self, key):
        return self.redis.hget(self.get_key(), key)

    def __setitem__(self, key, value):
        return self.redis.hset(self.get_key(), key, value)

    def __delitem__(self, key):
        return self.redis.hdel(self.get_key(), key)

    def __iter__(self):
        return self.redis.hkeys(self.get_key())

    def __contains__(self):
        return self.redis.hexists(self.get_key(), key)
