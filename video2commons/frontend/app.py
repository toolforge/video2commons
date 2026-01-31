#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2015-2016 Zhuyifei1999
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#

"""video2commons web frontend."""

import json
import logging
import traceback
from urllib.parse import urlparse, urljoin

from flask import Flask, request, Response, session, render_template, redirect, url_for
from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
from requests_oauthlib import OAuth1
import requests

from video2commons.config import (
    consumer_key,
    consumer_secret,
    api_url,
    webfrontend_uri,
    socketio_uri,
)

from video2commons.frontend.redisession import RedisSessionInterface
from video2commons.frontend.shared import redisconnection, check_banned
from video2commons.frontend.api import api, is_sudoer
from video2commons.frontend.i18n import (
    i18nblueprint,
    translate as _,
    getlanguage,
    is_rtl,
)

ISSUE_URL = "https://github.com/toolforge/video2commons/issues"

consumer_token = ConsumerToken(consumer_key, consumer_secret)
handshaker = Handshaker(api_url, consumer_token)

app = Flask(__name__)

app.logger.setLevel(logging.INFO)

app.session_cookie_name = "v2c-session"
app.session_interface = RedisSessionInterface(redisconnection)

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

config_p = {
    "webfrontend_uri": webfrontend_uri,
    "socketio_uri": socketio_uri,
}

app.jinja_env.globals["config"] = config_p
app.jinja_env.globals["_"] = _
app.jinja_env.globals["lang"] = getlanguage
app.jinja_env.tests["rtl"] = is_rtl

app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(i18nblueprint, url_prefix="/i18n")


@app.errorhandler(Exception)
def all_exception_handler(e):
    """Handle an exception and show the traceback to error page."""
    issue_link = f'<a href="{ISSUE_URL}">{ISSUE_URL}</a>'
    stacktrace = None

    try:
        message = (
            f"Please file an issue with this error in GitHub: {issue_link}<br><br>"
        )
        loggedin = "username" in session
        stacktrace = traceback.format_exc()
    except:
        message = (
            f"Something went terribly wrong, "
            f"and we failed to find the cause automatically. "
            f"Please file an issue in GitHub: {issue_link}"
        )
        loggedin = False

    try:
        return render_template(
            "error.min.html",
            html_message=message,
            stacktrace=stacktrace,
            loggedin=loggedin,
        ), 500
    except:
        return message, 500


@app.before_request
def force_https():
    """Force user to redirect to https, checking X-Forwarded-Proto."""
    if request.headers.get("X-Forwarded-Proto") == "http":
        return redirect(
            "https://" + request.headers["Host"] + request.headers["X-Original-URI"],
            code=301,
        )


@app.route("/config")
def get_config():
    """Get the current config as a dict and output Javascript."""
    data = "window.config=" + json.dumps(config_p) + ";"
    return Response(data, mimetype="application/javascript; charset=utf-8")


@app.route("/")
def main():
    """Main page."""
    banned = check_banned()
    if banned:
        return render_template(
            "error.min.html",
            message="You are banned from using this tool! Reason: " + banned,
            loggedin=False,
        )

    try:
        auth = dologin()
        session["language"] = querylanguage(auth)
    except:
        # SECURITY: If we cannot login, the session is invalid.
        app.session_interface.abandon_session(app, session)
        return render_template("main.min.html", loggedin=False)

    return render_template("main.min.html", loggedin=True)


def dologin():
    """Attempt to login."""
    if not ("access_token_key" in session and "access_token_secret" in session):
        raise NameError("No access keys")

    access_token = AccessToken(
        session["access_token_key"], session["access_token_secret"]
    )
    session["username"] = handshaker.identify(access_token)["username"]
    auth = OAuth1(
        client_key=consumer_token.key,
        client_secret=consumer_token.secret,
        resource_owner_key=access_token.key,
        resource_owner_secret=access_token.secret,
    )

    return auth


def querylanguage(auth):
    """Query user's language that's available on v2c."""
    default = "en"

    r = requests.post(
        url=api_url.replace("index.php", "api.php"),
        data={
            "action": "query",
            "format": "json",
            "meta": "userinfo",
            "uiprop": "options",
        },
        auth=auth,
    )

    try:
        language = r.json()["query"]["userinfo"]["options"]["language"]
    except (NameError, KeyError):
        return default

    if not language:
        return default

    return language


@app.route("/oauthinit")
def loginredirect():
    """Initialize OAuth login."""
    app.session_interface.abandon_session(app, session)

    redirecturl, request_token = handshaker.initiate()
    session["request_token_key"], session["request_token_secret"] = (
        request_token.key,
        request_token.secret,
    )
    session["return_to_url"] = url_for("main")

    returnto = request.args.get("returnto")
    if returnto:
        ref_url = urlparse(request.url_root)
        test_url = urlparse(urljoin(request.host_url, returnto))
        if (
            test_url.scheme == ref_url.scheme
            and test_url.netloc == ref_url.netloc
            and test_url.path.startswith(ref_url.path)
        ):
            session["return_to_url"] = returnto

    return redirect(redirecturl)


@app.route("/oauthcallback")
def logincallback():
    """Finialize OAuth login."""
    request_token = RequestToken(
        session["request_token_key"], session["request_token_secret"]
    )
    access_token = handshaker.complete(request_token, request.query_string)

    session.pop("access_token_key", None)
    session.pop("access_token_secret", None)
    session.pop("username", None)

    identify = handshaker.identify(access_token)

    is_contributor = identify["editcount"] >= 50
    is_maintainer = is_sudoer(identify["username"])
    is_autoconfirmed = "autoconfirmed" in identify["rights"]

    # Only allow autoconfirmed users either with at least 50 edits or
    # maintainer status to use this tool.
    if not (is_autoconfirmed and (is_contributor or is_maintainer)):
        return render_template(
            "error.min.html",
            message="You must be an autoconfirmed Commons user "
            "with at least 50 edits to use this tool.",
            loggedin=True,
        )

    session["access_token_key"], session["access_token_secret"] = (
        access_token.key,
        access_token.secret,
    )

    session["username"] = identify["username"]
    session["is_maintainer"] = is_maintainer

    return redirect(session.get("return_to_url", url_for("main")))


@app.route("/logout")
def logout():
    """Logout: clear all session data."""
    session.clear()

    return redirect(url_for("main"))
