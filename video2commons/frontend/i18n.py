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

"""video2commons web i18n module."""

from __future__ import absolute_import

import os
import json

from flask import Blueprint, Response, request, session, g
from video2commons.frontend.shared import redisconnection

i18nblueprint = Blueprint('i18n', __name__)

_dir = os.path.dirname(os.path.realpath(__file__))


@i18nblueprint.after_request
def max_age(response):
    """Set max_age of response to 5 mins."""
    response.cache_control.max_age = 3600
    return response


@i18nblueprint.route('/<lang>')
def urlget(lang):
    """Get the i18n of language lang and output Javascript."""
    data = 'window.i18n=' + json.dumps(get(lang)) + ';'
    return Response(data, mimetype='application/javascript; charset=utf-8')


def get(lang):
    """Get the i18n of language lang and output dict."""
    i18nkey = 'i18n:' + lang
    gval = g.get(i18nkey, None)
    if gval:
        return gval
    if redisconnection.exists(i18nkey):
        return json.loads(redisconnection.get(i18nkey))

    data = {}
    fallbacklist = _create_fallback(lang)
    datafiles = _loadi18nfiles(fallbacklist)
    for key in datafiles['en']:
        if key == '@metadata':
            # @metadata is a dict not a string
            continue

        for code in fallbacklist:
            if key in datafiles.get(code, {}):
                data[key] = datafiles[code][key]
                # <'s and >'s aren't supposed to be here;
                # if the translation breaks due to double escaping,
                # oh well, why are are you hacking this tool?
                # --XSS prevention
                data[key] = data[key].replace('<', '&lt;')
                data[key] = data[key].replace('>', '&gt;')
                break
    data['@dir'] = _dir(lang)

    setattr(g, i18nkey, data)
    redisconnection.setex(i18nkey, json.dumps(data), 60)
    return data


def _loadi18nfiles(fallbacklist):
    datafiles = {}
    for code in fallbacklist:
        if code not in datafiles:
            path = _dir + '/i18n/' + code + '.json'
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    datafiles[code] = json.load(f)
    return datafiles


def _create_fallback(lang):
    fallbacks = _loadmetadatafile('fallbacks').get(lang, [])
    fallbacks = fallbacks if isinstance(fallbacks, list) else [fallbacks]
    return [lang] + fallbacks + ['en']


def translate(key):
    """Translate a key in user language."""
    return get(getlanguage()).get(key, '&lt;' + key + '&gt;')


def getlanguage():
    """Get the user language."""
    gval = g.get('language', None)
    if gval:
        return gval

    for lang in [
        request.form.get('uselang'),
        request.args.get('uselang'),
        session.get('language'),
        request.accept_languages.best,
    ]:
        if lang and _islang(lang):
            break
    else:
        lang = 'en'

    g.language = lang

    return lang


def _loadmetadatafile(metadata):
    key = 'i18nmeta-' + metadata
    gval = g.get(key, None)
    if gval:
        return gval

    path = _dir + '/i18n-metadata/' + metadata + '.json'
    with open(path, 'r') as f:
        data = json.load(f)

    setattr(g, key, data)
    return data


def _islang(lang):
    return lang in _loadmetadatafile('alllangs')


def _dir(lang):
    return 'rtl' if lang in _loadmetadatafile('rtl') else 'ltr'
