#!/usr/bin/env python
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

"""video2commons web frontend."""

from __future__ import absolute_import

import os
import traceback

from flask import (
    Flask, request, session, render_template, redirect, url_for
)
from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
from requests_oauthlib import OAuth1
import requests
from video2commons.config import consumer_key, consumer_secret, api_url

from video2commons.frontend.redisession import RedisSessionInterface
from video2commons.frontend.shared import (
    redisconnection, check_banned, generate_csrf_token
)
from video2commons.frontend.api import api

consumer_token = ConsumerToken(consumer_key, consumer_secret)
handshaker = Handshaker(api_url, consumer_token)

app = Flask(__name__)

app.session_interface = RedisSessionInterface(redisconnection)

app.register_blueprint(api, url_prefix='/api')

app.jinja_env.globals['csrf_token'] = generate_csrf_token


@app.errorhandler(Exception)
def all_exception_handler(e):
    """Handle an exception and show the traceback to error page."""
    try:
        message = 'Please notify [[c:User:Zhuyifei1999]]: ' + \
                  traceback.format_exc()
        loggedin = 'username' in session
    except:
        message = (
            'Something went terribly wrong, '
            'and we failed to find the cause automatically. '
            'Please notify [[c:User:Zhuyifei1999]].'
        )
        loggedin = False
    try:
        return render_template(
            'error.min.html',
            message=message,
            loggedin=loggedin
        ), 500
    except:
        return 500


@app.before_request
def force_https():
    """Force user to redirect to https, checking X-Forwarded-Proto."""
    if request.headers.get('X-Forwarded-Proto') == 'http':
        return redirect('https://' + request.headers['Host'] +
                        request.headers['X-Original-URI'])


@app.route('/')
def main():
    """Main page."""
    banned = check_banned()
    if banned:
        return render_template(
            'error.min.html',
            message='You are banned from using this tool! Reason: ' + banned,
            loggedin=False
        )

    try:
        auth = dologin()
        session['language'] = querylanguage(auth)
    except:
        return render_template('main.min.html', loggedin=False)

    return render_template(
        'main.min.html',
        loggedin=True,
        lang=session['language']
    )


def dologin():
    """Attempt to login."""
    if not (
        'access_token_key' in session and
        'access_token_secret' in session
    ):
        raise NameError("No access keys")

    access_token = AccessToken(
        session['access_token_key'],
        session['access_token_secret']
    )
    session['username'] = handshaker.identify(access_token)['username']
    auth = OAuth1(
        client_key=consumer_token.key,
        client_secret=consumer_token.secret,
        resource_owner_key=access_token.key,
        resource_owner_secret=access_token.secret
    )

    return auth


def querylanguage(auth):
    """Query user's language that's available on v2c."""
    default = 'en'

    r = requests.post(
        url=api_url.replace('index.php', 'api.php'),
        data={
            'action': 'query',
            'format': 'json',
            'meta': 'userinfo',
            'uiprop': 'options'
        },
        auth=auth
    )

    try:
        language = r.json()['query']['userinfo']['options']['language']
    except (NameError, KeyError):
        return default

    if not language:
        return default

    if os.path.isfile(
        os.path.dirname(os.path.realpath(__file__)) +
        '/static/i18n/' + language + '.min.js'
    ):
        return language
    elif '-' in language and os.path.isfile(
        os.path.dirname(os.path.realpath(__file__)) +
        '/static/i18n/' + language.split('-')[0] + '.min.js'
    ):
        return language.split('-')[0]
    else:
        return default


@app.route('/oauthinit')
def loginredirect():
    """Initialize OAuth login."""
    redirecturl, request_token = handshaker.initiate()
    session['request_token_key'], session['request_token_secret'] = \
        request_token.key, request_token.secret

    return redirect(redirecturl)


@app.route('/oauthcallback')
def logincallback():
    """Finialize OAuth login."""
    request_token = RequestToken(
        session['request_token_key'],
        session['request_token_secret']
    )
    access_token = handshaker.complete(request_token, request.query_string)

    session.pop('access_token_key', None)
    session.pop('access_token_secret', None)
    session.pop('username', None)

    identify = handshaker.identify(access_token)
    if not (identify['editcount'] >= 50 and
            'autoconfirmed' in identify['rights']):
        return render_template(
            'error.min.html',
            message='Due to ongoing abuse, you must be autoconfirmed '
                    'with at least 50 edits on Commons to use this tool.',
            loggedin=True
        )

    session['access_token_key'], session['access_token_secret'] = \
        access_token.key, access_token.secret

    session['username'] = identify['username']

    return redirect(url_for('main'))


@app.route('/logout')
def logout():
    """Logout: clear all session data."""
    session.clear()

    return redirect(url_for('main'))
