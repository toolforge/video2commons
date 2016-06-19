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
# along with this program.  If not, see <http://www.gnu.org/licenses/>`
#

"""video2commons web API."""

from __future__ import absolute_import

import pickle
import traceback
import urllib

from flask import (
    Blueprint, request, session, jsonify
)

from video2commons.backend import worker
from video2commons.exceptions import NeedServerSideUpload

from video2commons.frontend.shared import (
    redisconnection, check_banned, generate_csrf_token
)
from video2commons.frontend.urlextract import (
    do_extract_url, do_validate_filename, sanitize
)

api = Blueprint('api', __name__)


@api.errorhandler(Exception)
def all_exception_handler(e):
    """Handle an exception and return an error JSON responce."""
    return error_json(e)


@api.before_request
def check_logged_in():
    """Error if a user is not logged in."""
    if 'username' not in session:
        return error_json('Are you logged in?')


@api.before_request
def csrf_protect():
    """For POSTs, require CSRF token."""
    if request.method == "POST":
        token = session.get('_csrf_token')
        if not token or token != request.form.get('_csrf_token'):
            return error_json('Invalid CSRF token. Try reloading this page.')


def format_exception(e):
    """Format an exception to text."""
    try:
        desc = str(e)
    except UnicodeError:
        desc = u'%s' % e

    try:
        desc = str(desc.encode('utf-8'))
    except UnicodeError:
        desc = str(desc.decode('utf-8').encode('utf-8'))

    if isinstance(e, AssertionError):
        return desc
    else:
        return 'An exception occurred: %s: %s' % \
            (type(e).__name__, desc)


def error_json(e):
    """Get a JSON responce on error."""
    session.rollback()
    if isinstance(e, BaseException):
        return jsonify(
            step='error',
            error=format_exception(e),
            traceback=traceback.format_exc()
        )
    else:
        return jsonify(
            step='error',
            error=e,
            traceback=None
        )


@api.route('/csrf')
def get_csrf():
    """Get the CSRF token for API-only access."""
    return jsonify(
        csrf=generate_csrf_token()
    )


@api.route('/status')
def status():
    """Get all visible task status for user."""
    ids = get_tasks()
    goodids = []
    values = []
    ssus = []
    hasrunning = False
    for id in ids:
        title = get_title_from_task(id)
        if not title:
            # task has been forgotten -- results should have been expired
            continue
        goodids.append(id)
        res = worker.main.AsyncResult(id)
        task = {
            'id': id,
            'title': title
        }

        try:
            state = res.state
        except:
            task.update({
                'status': 'fail',
                'text': 'The status of the task could not be retrieved.',
                'traceback': traceback.format_exc()
            })
        else:
            if state == 'PENDING':
                task.update({
                    'status': 'progress',
                    'text': 'Your task is pending...',
                    'progress': -1
                })
                hasrunning = True
            elif state == 'STARTED':
                task.update({
                    'status': 'progress',
                    'text': 'Your task has been started; preprocessing...',
                    'progress': -1
                })
                hasrunning = True
            elif state == 'PROGRESS':
                task.update({
                    'status': 'progress',
                    'text': res.result['text'],
                    'progress': res.result['percent']
                })
                hasrunning = True
            elif state == 'SUCCESS':
                filename, wikifileurl = res.result
                task.update({
                    'status': 'done',
                    'url': wikifileurl,
                    'text': filename
                })
            elif state == 'FAILURE':
                e = res.result
                if e is False:
                    task.update({
                        'status': 'fail',
                        'text': res.traceback,
                        'restartable': True
                    })
                elif isinstance(e, NeedServerSideUpload):
                    task.update({
                        'status': 'needssu',
                        'url': create_phab_url([e])
                    })
                    ssus.append(e)
                else:
                    task.update({
                        'status': 'fail',
                        'text': format_exception(e),
                        'restartable': (
                            (not redisconnection.exists('restarted:' + id)) and
                            redisconnection.exists('params:' + id)
                        )
                    })
            elif state == 'ABORTED':
                task.update({
                    'status': 'abort',
                    'text': 'Your task is being aborted...'
                })
                hasrunning = True
            else:
                task.update({
                    'status': 'fail',
                    'text': 'Something weird going on. ' +
                            'Please notify [[commons:User:Zhuyifei1999]]'
                })

        values.append(task)

    ssulink = create_phab_url(ssus) if ssus else ''

    return jsonify(
        ids=goodids,
        values=values,
        hasrunning=hasrunning,
        ssulink=ssulink
    )


def is_sudoer(username):
    """Check if a user is a sudoer."""
    return username in redisconnection.lrange('sudoers', 0, -1)


def get_tasks():
    """Get a list of visible tasks for user."""
    # sudoer = able to monitor all tasks
    username = session['username']
    if is_sudoer(username):
        key = 'alltasks'
    else:
        key = 'tasks:' + username

    return redisconnection.lrange(key, 0, -1)[::-1]


def get_title_from_task(id):
    """Get task title from task ID."""
    return redisconnection.get('titles:' + id)


def create_phab_url(es):
    """Create a server side upload Phabricator URL."""
    import pipes

    wgetlinks = []

    for e in es:
        wgetlink = 'wget ' + pipes.quote(e.url) + '{,.txt}'
        if e.hashsum:
            wgetlink += ' # ' + e.hashsum
        wgetlinks.append(wgetlink)

    wgetlinks = '\n'.join(wgetlinks)
    # Partial Source: videoconverter tool
    phabdesc = """Please upload these file(s) to Wikimedia Commons:
```
%s
```
Thank you!""" % (wgetlinks)

    phaburl = \
        'https://phabricator.wikimedia.org/maniphest/task/edit/form/1/?' + \
        'title=Please%20upload%20large%20file%20to%20Wikimedia%20Commons&' + \
        'projects=Wikimedia-Site-requests,commons&description=' + \
        urllib.quote(phabdesc.encode('utf-8'))
    return phaburl


@api.route('/extracturl', methods=['POST'])
def extract_url():
    """Extract a video url."""
    url = request.form['url']

    return jsonify(**do_extract_url(url))


@api.route('/listformats', methods=['POST'])
def list_formats():
    """List the possible convert formats from a given audio/video pair."""
    formats = []
    prefer = ''
    video = _boolize(request.form['video'])
    audio = _boolize(request.form['audio'])
    if video:
        if audio:
            formats = ['ogv (Theora/Vorbis)', 'webm (VP8/Vorbis)',
                       'webm (VP9/Opus, experimental)']
            prefer = 'webm (VP8/Vorbis)'
        else:
            formats = ['ogv (Theora)', 'webm (VP8)',
                       'webm (VP9, experimental)']
            prefer = 'webm (VP8)'
    else:
        if audio:
            formats = ['ogg (Vorbis)', 'opus (Opus, experimental)']
            prefer = 'ogg (Vorbis)'
        else:
            raise RuntimeError('Either video or audio must be kept')

    return jsonify(
        audio=audio,
        video=video,
        format=prefer,
        formats=formats
    )


def _boolize(data):
    return data in [True, 'true', 'TRUE', 'True', 1, '1']


@api.route('/validatefilename', methods=['POST'])
def validate_filename():
    """Validate filename for invalid characters/parts."""
    return jsonify(
        filename=do_validate_filename(request.form['filename'])
    )


def get_backend_keys(format):
    """Get the youtube-dl download format key."""
    return {
        'ogv (Theora)':
            ('bestvideo/best', 'an.ogv'),
        'webm (VP8)':
            ('bestvideo/best', 'an.webm'),
        'webm (VP9, experimental)':
            ('bestvideo/best', 'an.vp9.webm'),
        'ogg (Vorbis)':
            ('bestaudio/best', 'ogg'),
        'opus (Opus, experimental)':
            ('bestaudio/best', 'opus'),
        'ogv (Theora/Vorbis)':
            ('bestvideo+bestaudio/best', 'ogv'),
        'webm (VP8/Vorbis)':
            ('bestvideo+bestaudio/best', 'webm'),
        'webm (VP9/Opus, experimental)':
            ('bestvideo+bestaudio/best', 'vp9.webm'),
    }[format]


@api.route('/task/run', methods=['POST'])
def run_task():
    """Run a task with parameters from session."""
    url = request.form['url']
    ie_key = request.form['extractor']
    subtitles = request.form['subtitles']
    filename = sanitize(request.form['filename'])
    filedesc = request.form['filedesc']
    downloadkey, convertkey = get_backend_keys(request.form['format'])
    username = session['username']
    oauth = (session['access_token_key'], session['access_token_secret'])

    taskid = run_task_internal(filename, (
        url, ie_key, subtitles, filename, filedesc,
        downloadkey, convertkey, username, oauth
    ))

    return jsonify(id=taskid, step='success')


def run_task_internal(filename, params):
    """Internal run task function to accept whatever params given."""
    banned = check_banned()
    assert not banned, 'You are banned from using this tool! Reason: ' + banned

    res = worker.main.delay(*params)
    taskid = res.id

    expire = 14 * 24 * 3600  # 2 weeks
    redisconnection.lpush('alltasks', taskid)
    redisconnection.expire('alltasks', expire)
    redisconnection.lpush('tasks:' + session['username'], taskid)
    redisconnection.expire('tasks:' + session['username'], expire)
    redisconnection.set('titles:' + taskid, filename)
    redisconnection.expire('titles:' + taskid, expire)
    redisconnection.set('params:' + taskid, pickle.dumps(params))
    redisconnection.expire('params:' + taskid, expire)

    return taskid


@api.route('/task/restart', methods=['POST'])
def restart_task():
    """Reastart a task: run a task with params of another task."""
    id = request.form['id']

    filename = redisconnection.get('titles:' + id)
    assert filename, 'Task does not exist'
    assert id in \
        redisconnection.lrange('tasks:' + session['username'], 0, -1), \
        'Task must belong to you.'

    restarted = redisconnection.get('restarted:' + id)
    assert not restarted, \
        'Task has already been restarted with id ' + restarted
    params = redisconnection.get('params:' + id)
    assert params, 'Could not extract the task parameters.'

    newid = run_task_internal(filename, pickle.loads(params))
    redisconnection.set('restarted:' + id, newid)

    return jsonify(restart='success', id=id, taskid=newid)


@api.route('/task/remove', methods=['POST'])
def remove_task():
    """Revove a task from list of tasks."""
    id = request.form['id']
    username = session['username']
    assert id in \
        redisconnection.lrange('tasks:' + username, 0, -1), \
        'Task must belong to you.'
    redisconnection.lrem('alltasks', id)  # not StrictRedis
    redisconnection.lrem('tasks:' + username, id)  # not StrictRedis
    redisconnection.delete('titles:' + id)
    redisconnection.delete('params:' + id)
    redisconnection.delete('restarted:' + id)
    return jsonify(remove='success', id=id)


@api.route('/task/abort', methods=['POST'])
def abort_task():
    """Abort a task."""
    id = request.form['id']
    username = session['username']
    assert id in \
        redisconnection.lrange('tasks:' + username, 0, -1), \
        'Task must belong to you.'
    worker.main.AsyncResult(id).abort()
    return jsonify(remove='success', id=id)
