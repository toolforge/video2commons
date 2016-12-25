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

from __future__ import absolute_import

import os
import re
import uuid
import shutil

from flask import request, jsonify

RE_CONTENT_RANGE = re.compile(r'^bytes (\d+)-(\d+)/(\d+)$')


class WrongOffset(Exception):
    pass


def getpath(digest):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        'static/uploads', digest)


def stat(permpath):
    return os.path.getsize(permpath)


# Flask endpoint
def upload():
    f = request.files['file']
    assert f, "Where's my file?"

    filekey = request.form.get('filekey') or str(uuid.uuid1())

    permpath = getpath(filekey)

    content_range = (f.headers.get('Content-Range') or
                     request.headers.get('Content-Range'))

    if content_range:
        result, kwargs = handle_chunked(f, permpath, content_range)
    else:
        result, kwargs = handle_full(f, permpath)

    kwargs['filekey'] = filekey

    return jsonify(result=result, **kwargs)


# Flask endpoint
def status():
    permpath = getpath(request.form['filekey'])
    return jsonify(offset=stat(permpath))


def handle_full(f, permpath):
    f.save(permpath)
    return 'Success', {}


def handle_chunked(f, permpath, content_range):
    try:
        content_range = RE_CONTENT_RANGE.match(content_range)
        assert content_range, 'Invalid content range!'

        cr1, cr2, cr3 = [int(content_range.group(i)) for i in range(1, 4)]

        if os.path.isfile(permpath):
            size = stat(permpath)
            if size != cr1:
                raise WrongOffset

            with open(permpath, 'ab') as dest:
                shutil.copyfileobj(f, dest)
        else:
            f.save(permpath)
    except WrongOffset:
        pass

    size = stat(permpath)
    if size < cr3:
        return 'Continue', {'offset': size}
    elif size > cr3:
        raise RuntimeError('What?! Uploaded file is larger than '
                           'what it is supposed to be?')
    return 'Success', {}
