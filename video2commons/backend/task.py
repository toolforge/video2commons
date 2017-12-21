#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General License for more details.
#
# You should have received a copy of the GNU General License
# along with self program.  If not, see <http://www.gnu.org/licenses/>
#

"""video2commons backend task."""

from __future__ import absolute_import, unicode_literals

import collections
import contextlib
import os

from celery.exceptions import Ignore
from redis import Redis

from video2commons.config import (
    redis_pw, redis_host, consumer_key, consumer_secret
)
from video2commons.exceptions import TaskError, TaskAbort, NeedServerSideUpload
from video2commons.backend.contexts import outputdir, pwb_login
from video2commons.backend import download, encode, upload, subtitles

redisconnection = Redis(host=redis_host, db=3, password=redis_pw)


class TaskStatus(object):
    __slots__ = ('_task', '_writeimmediate', '_needwrite', '_text', '_percent')

    def __init__(self, task):
        self._task = task
        self._writeimmediate = True
        self._needwrite = False
        self._text = 'PREINIT'
        self._percent = -1

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, val):
        if val != self._text:
            self._text = val
            self._write()

    @property
    def percent(self):
        return self._percent

    @percent.setter
    def percent(self, val):
        if val != self._percent:
            self._percent = val
            self._write()

    @contextlib.contextmanager
    def _pause(self):
        """
        Pause writing the status to the result backend.

        By default, status will be immediately written. In this context it will
        be paused, but the new status will be written immediately, if
        necessary, upon complete exit of this context.

        This context manager is reentrant.
        """

        old_wi = self._writeimmediate
        self._writeimmediate = False
        try:
            yield
        finally:
            assert not self._writeimmediate
            self._writeimmediate = old_wi
            if self._writeimmediate and self._needwrite:
                self._write()

    def _write(self):
        if self._task.celery.is_aborted():
            raise TaskAbort

        if self._writeimmediate:
            self._task.celery.update_state(
                state='PROGRESS',
                meta={'text': self.text, 'percent': self.percent}
            )
            self._needwrite = False
        else:
            self._needwrite = True


def TaskArgs(_args):
    _nt = collections.namedtuple('nt_ArgType', _args)
    _args = set(_args)
    # ArgType = None  # closure variable placeholder, needed for super()

    # __slots__ = ('_whitelist', '_tainted')
    # TODO: save _tainted

    def __init__(self, *args, **kwargs):
        super(ArgType, self).__init__(*args, **kwargs)
        self._whitelist = None
        self._tainted = set()

    def _taint(self, lst):
        lst = set(lst)
        assert lst.issubset(_args)
        self._tainted.update(lst)

    @contextlib.contextmanager
    def _whitelisted(self, lst):
        assert self._whitelist is None
        lst = set(lst)
        assert lst.issubset(_args)
        self._whitelist = lst

        try:
            yield
        finally:
            assert self._whitelist is lst
            self._whitelist = None

    def __getattribute__(self, name):
        if name[0] != '_':
            if self._whitelist is not None:
                assert name in self._whitelist
        return super(ArgType, self).__getattribute__(name)

    ArgType = type(str('ArgType'), (_nt,), locals())
    return ArgType


class BaseTask(object):
    ArgType = TaskArgs([])

    def __init__(self, celery, *args, **kwargs):
        self.celery = celery
        self.status = TaskStatus(self)
        self.args = self.ArgType(*args, **kwargs)
        self.results = {}

        self.preinit()

        with self.status._pause():
            self.status.text = 'Initializing...'
            self.status.percent = -1

    def error(self, msg):
        if isinstance(msg, Exception):
            raise msg
        raise TaskError(msg)

    def preinit(self):
        # Get a lock to prevent double-running with same task ID
        lockkey = 'tasklock:' + self.celery.request.id
        if redisconnection.exists(lockkey):
            raise Ignore

        if not self.check_requirements():
            self.celery.retry(max_retries=20, countdown=5*60)
            assert False  # should never reach here

        redisconnection.setex(lockkey, 'T', 7 * 24 * 3600)

    def check_requirements(self):
        return True

    def run(self):
        with self.context():
            return self._run()

            with self.status._pause():
                self.status.text = 'Done!'
                self.status.percent = 100

    def _run(self):
        pass

    @contextlib.contextmanager
    def context(self):
        """Noop context."""
        yield

    def execute_module(self, module, function, startmsg, argswhitelist):
        # pause/resume mechanism: if we already got the result then skip it
        if module not in self.results:
            with self.status._pause():
                self.status.text = startmsg
                self.status.percent = -1

            with self.args._whitelisted(argswhitelist):
                self.results[module] = function(self)
        else:
            # Check if the results are made from the same set of args
            assert self.args._tainted.isdisjoint(argswhitelist)

        return self.results[module]


class v2cTask(BaseTask):
    ArgType = TaskArgs([
        'url', 'ie_key', 'subtitles', 'filename', 'filedesc',
        'downloadkey', 'convertkey', 'username', 'oauth'
    ])

    def check_requirements(self):
        # Check for 10G of disk space, refuse to run if it is unavailable
        st = os.statvfs('/srv')
        return st.f_frsize * st.f_bavail > 10 << 30

    @contextlib.contextmanager
    def context(self):
        with outputdir():
            yield

    def _run(self):
        self.execute_module(
            'download', download.download, 'Downloading...',
            ['url', 'downloadkey', 'subtitles', 'ie_key'])
        self.execute_module(
            'encode', encode.encode, 'Converting...',
            ['convertkey'])

        with pwb_login(
            self.args.username,
            (consumer_key, consumer_secret) + tuple(self.args.oauth)
        ):
            try:
                self.execute_module(
                    'upload', upload.upload, 'Uploading...',
                    ['filename', 'filedesc', 'username', 'url'])
            except NeedServerSideUpload as e:
                # json serializer cannot properly serialize an exception
                # without losing data, so we change the exception into a dict.
                return {
                    'type': 'ssu',
                    'hashsum': e.hashsum,
                    'url': e.url
                }

            if self.args.subtitles:
                self.execute_module(
                    'subtitles', subtitles.subtitles, 'Uploading subtitles...',
                    ['username'])

            filename, fileurl = self.results['upload']
            return {
                'type': 'done',
                'filename': filename,
                'url': fileurl
            }
