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

from flask import Flask, request, Response, session, render_template, redirect, url_for
# https://github.com/mediawiki-utilities/python-mwoauth
from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
import requests
from requests_oauthlib import OAuth1
from config import consumer_key, consumer_secret, api_url, session_key

consumer_token = ConsumerToken(consumer_key, consumer_secret)
handshaker = Handshaker(api_url, consumer_token)

app = Flask(__name__)

app.secret_key = session_key

@app.errorhandler(Exception)
def all_exception_handler(error):
    return 'Please notify [[commons:User:Zhuyifei1999]]: ' + type(error).__name__ + ': ' + str(error), 500

@app.route('/')
def main():
    try:
        dologin()
    except:
        return render_template('bootstraphtml.html', loggedin=False,
            content='<form method="get" action="' + \
            url_for('loginredirect') + \
            '"><center><input class="btn btn-primary btn-success btn-large" value="Login on Wikimedia Commons" type="submit"></center></form>')

    return render_template('bootstraphtml.html', loggedin=True, content='<noscript>Javascript is Required to use this tool!</noscript>')

def dologin():
    if not ('access_token_key' in session and 'access_token_secret' in session):
        raise NameError("No access keys")

    access_token = AccessToken(session['access_token_key'], session['access_token_secret'])
    #identity = 
    handshaker.identify(access_token)
    return OAuth1(consumer_token.key,
            client_secret=consumer_token.secret,
            resource_owner_key=access_token.key,
            resource_owner_secret=access_token.secret
        )

@app.route('/oauthinit')
def loginredirect():
    redirecturl, request_token = handshaker.initiate()
    session['request_token_key'], session['request_token_secret'] = request_token.key, request_token.secret

    return redirect(redirecturl)


@app.route('/oauthcallback')
def logincallback():
    request_token = RequestToken(session['request_token_key'], session['request_token_secret'])
    access_token = handshaker.complete(request_token, request.query_string)
    session['access_token_key'], session['access_token_secret'] = access_token.key, access_token.secret

    return redirect(url_for('main'))

@app.route('/logout')
def logout():
    session.pop('request_token_key', None)
    session.pop('request_token_secret', None)
    session.pop('access_token_key', None)
    session.pop('access_token_secret', None)

    return redirect(url_for('main'))

if __name__ == '__main__':
    app.run()