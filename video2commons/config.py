#! /usr/bin/python
# -*- coding: UTF-8 -*-
#

"""v2c config loading from json."""

import os as _os
import json as _json

try:
    tooldir = _os.path.dirname(_os.path.realpath(__file__))
    if tooldir.startswith("/workspace"):  # we are in buildpack
        tooldir = _os.path.expandvars("$TOOL_DATA_DIR/video2commons")
    with open(tooldir + "/../config.json", "r") as _f:
        _data = _json.load(_f)
except IOError as _e:
    __import__("logging").exception(_e)
    _data = {}

consumer_key = _data.get("consumer_key")
consumer_secret = _data.get("consumer_secret")
api_url = _data.get("api_url")
redis_pw = _data.get("redis_pw")
redis_host = _data.get("redis_host")
session_key = _data.get("session_key")
http_host = _data.get("http_host")
webfrontend_uri = _data.get("webfrontend_uri")
socketio_uri = _data.get("socketio_uri")
youtube_user = _data.get("youtube_user")
youtube_pass = _data.get("youtube_pass")
