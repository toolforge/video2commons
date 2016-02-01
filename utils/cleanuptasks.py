#!/usr/bin/env python
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

import sys
from redis import Redis

sys.path.append(os.path.dirname(os.path.realpath(__file__))+"/../")
from config import redis_pw

redisconnection = Redis(host='encoding01.video.eqiad.wmflabs', db=3, password=redis_pw)

for userkey in redisconnection.keys('tasks:*'):
    for id in redisconnection.lrange(userkey, 0, -1):
        if not redisconnection.exists('titles:' + id):
            redisconnection.lrem(userkey, id)
            print "delete %s from %s" % (id, userkey)
