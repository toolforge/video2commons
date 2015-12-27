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

from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
import requests
from requests_oauthlib import OAuth1
from config import consumer_key, consumer_secret, api_url
from session import Session
from bootstraphtml import bootstraphtml

class video2commons(object):
    def __init__(self):
        self.session = Session()
        self.consumer_token = ConsumerToken(consumer_key, consumer_secret)
        self.handshaker = Handshaker("https://en.wikipedia.org/w/index.php", consumer_token)
        self.session = Session()
        
    def printheader(self):
        print "HTTP/1.1 200 OK"
        print self.session.as_cookie()
        print
        print bootstraphtml

    def webstart(self):
        try:
            self.dologin()
        except:
            return self.displayloginform()

        printheader()
        print 'You are now logged in.'

    def dologin(self):
        if not ('access_token_key' in self.session and 'access_token_secret' in self.session):
            raise NameError("No access keys")

        self.auth1 = OAuth1(self.consumer_token.key,
               client_secret=self.consumer_token.secret,
               resource_owner_key=self.session['access_token_key'],
               resource_owner_secret=self.session['access_token_secret'])

    def displayloginform(self):
        self.printheader()
        print '<form method="get" action="oauthinit.py"><center><input class="btn btn-primary btn-success btn-large" value="Login on Wikimedia Commons" type="submit"></center></form>'

    def loginredirect(self):
        redirect, request_token = self.handshaker.initiate()
        self.session['request_token_key'], self.session['request_token_secret'] = request_token.key, request_token.secret
        print "HTTP/1.1 302 Found"
        print "Location: " + redirect
        return
        
    def logincallback(self):
        request_token = RequestToken(self.session['request_token_key'], self.session['request_token_secret'])
        access_token = self.handshaker.complete(request_token, os.environ.get("QUERY_STRING"))
        self.session['access_token_key'], self.session['access_token_secret'] = access_token.key, access_token.secret
        identity = self.handshaker.identify(access_token)
        print "HTTP/1.1 302 Found"
        print "Location: index.py"
        return
