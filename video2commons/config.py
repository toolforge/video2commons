#! /usr/bin/python
# -*- coding: UTF-8 -*-
#

"""v2c config loading from json."""

import os as _os
import json as _json

try:
    with open(_os.path.dirname(_os.path.realpath(__file__)) +
              '/../config.json', 'r') as f:
        _data = _json.load(f)
except IOError as _e:
    __import__('logging').exception(_e)
    _data = {}

consumer_key = _data.get('consumer_key')
consumer_secret = _data.get('consumer_secret')
api_url = _data.get('api_url')
redis_pw = _data.get('redis_pw')
redis_host = _data.get('redis_host')
session_key = _data.get('session_key')
http_host = _data.get('http_host')
