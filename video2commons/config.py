# -*- coding: UTF-8 -*-
#

"""v2c config loading from json."""

import json as _json
import logging as _logging
import os as _os
import re as _re

try:
    tooldir = _os.path.dirname(_os.path.realpath(__file__))
    if tooldir.startswith("/workspace"):  # we are in buildpack
        tooldir = _os.path.expandvars("$TOOL_DATA_DIR/video2commons")
    with open(tooldir + "/../config.json", "r") as _f:
        _data = _json.load(_f)
except OSError as _e:
    __import__("logging").exception(_e)
    _data = {}

_logger = _logging.getLogger(__name__)

# An origin, as a browser sends it: HTTPS, or HTTP on this computer for
# development. No path, no wildcard.
_ORIGIN = _re.compile(r"^(https://[a-z0-9.-]+|http://(localhost|127\.0\.0\.1))(:\d+)?$")


def parse_api_origins(value):
    """Get the origins that api_origins lists, as a frozenset.

    API tokens are sent to these origins, so whatever is not an origin is left
    out rather than allowed: a wildcard, a URL with a path, or a value that is
    not a list. A single origin given as a string is read as a list of one.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        if value is not None:
            _logger.error("api_origins is not a list of origins: %r", value)
        return frozenset()
    origins = set()
    for origin in value:
        normal = origin.strip().rstrip("/").lower() if isinstance(origin, str) else ""
        if _ORIGIN.match(normal):
            origins.add(normal)
        else:
            _logger.error("api_origins: %r is not an origin, left out", origin)
    return frozenset(origins)


def parse_api_max_active_tasks(value, default=3):
    """Get api_max_active_tasks: a whole number of at least 1, or the default.

    Anything else is left out, with an error in the log, rather than refusing
    every task of a tool, or failing on each one.
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _logger.error(
            "api_max_active_tasks is not a whole number of at least 1: %r", value
        )
        return default
    return value


consumer_key = _data.get("consumer_key")
consumer_secret = _data.get("consumer_secret")
api_url = _data.get("api_url")
redis_pw = _data.get("redis_pw")
redis_host = _data.get("redis_host")
session_key = _data.get("session_key")
webfrontend_uri = _data.get("webfrontend_uri")
socketio_uri = _data.get("socketio_uri")
youtube_user = _data.get("youtube_user")
youtube_pass = _data.get("youtube_pass")
# The sites whose pages may use the API with a token from /connect, e.g. a
# user script on Commons that sends its videos to video2commons. None until
# they are listed here: opening the API to the scripts of a site is for the
# maintainers to decide, and emptying the list closes it again.
api_origins = parse_api_origins(_data.get("api_origins"))
# How many tasks of a user may wait or run when a tool starts one more with a
# token. The encoders are shared by everyone, and a batch tool could otherwise
# queue a whole folder at once. The page of video2commons is not held to it.
api_max_active_tasks = parse_api_max_active_tasks(_data.get("api_max_active_tasks"))
