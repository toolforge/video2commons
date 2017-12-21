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

"""video2commons backend worker."""

from __future__ import absolute_import, print_function

import celery
from celery.contrib.abortable import AbortableTask

from video2commons.backend.task import v2cTask
from video2commons.config import redis_pw, redis_host

redisurl = 'redis://:' + redis_pw + '@' + redis_host + ':6379/'
app = celery.Celery(
    'v2cbackend',
    backend=redisurl + '1',
    broker=redisurl + '2'
)
app.conf.CELERY_TASK_RESULT_EXPIRES = 30 * 24 * 3600  # 1 month

app.conf.CELERY_ACCEPT_CONTENT = ['json']


@app.task(bind=True, track_started=False, base=AbortableTask)
def main(self, *args, **kwargs):
    """Main worker code."""

    return v2cTask(self, *args, **kwargs).run()
