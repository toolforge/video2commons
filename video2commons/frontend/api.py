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

import re
import pickle
import traceback
import urllib

from flask import (
    Blueprint, request, session, jsonify
)
import youtube_dl
import guess_language

from video2commons.backend import worker
from video2commons.exceptions import NeedServerSideUpload

from video2commons.frontend.shared import redisconnection, check_banned

api = Blueprint('api', __name__)


@api.errorhandler(Exception)
def all_exception_handler(e):
    """Handle an exception and return an error JSON responce."""
    return error_json(e)


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
        return 'An exception occured: %s: %s' % \
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
                task['status'] = 'fail'
                task['text'] = \
                    'The status of the task could not be retrieved.'
                task['traceback'] = traceback.format_exc()
        else:
            if state == 'PENDING':
                task['status'] = 'progress'
                task['text'] = 'Your task is pending...'
                task['progress'] = -1
                hasrunning = True
            elif state == 'STARTED':
                task['status'] = 'progress'
                task['text'] = 'Your task has been started; preprocessing...'
                task['progress'] = -1
                hasrunning = True
            elif state == 'PROGRESS':
                task['status'] = 'progress'
                task['text'] = res.result['text']
                task['progress'] = res.result['percent']
                hasrunning = True
            elif state == 'SUCCESS':
                task['status'] = 'done'
                filename, wikifileurl = res.result
                task['url'] = wikifileurl
                task['text'] = filename
            elif state == 'FAILURE':
                e = res.result
                if e is False:
                    task['status'] = 'fail'
                    task['text'] = res.traceback
                    task['restartable'] = True
                elif isinstance(e, NeedServerSideUpload):
                    task['status'] = 'needssu'
                    ssus.append(e)
                    task['url'] = create_phab_url([e])
                else:
                    task['status'] = 'fail'
                    task['text'] = format_exception(e)
                    task['restartable'] = (
                        (not redisconnection.exists('restarted:' + id)) and
                        redisconnection.exists('params:' + id)
                    )
            elif state == 'ABORTED':
                task['status'] = 'abort'
                if redisconnection.exists('restarted:' + id):
                    task['text'] = 'Your task is being aborted by an admin...'
                else:
                    task['text'] = 'Your task is being aborted...'
                hasrunning = True
            else:
                task['status'] = 'fail'
                task['text'] = 'Something weird going on. ' + \
                    'Please notify [[commons:User:Zhuyifei1999]]'

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

    params = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': '/dev/null',
        'writedescription': True,
        'writeinfojson': True,
        'writesubtitles': False,
        'subtitlesformat': 'srt/ass/vtt/best',
        'cachedir': '/tmp/',
        'noplaylist': True,  # not implemented in video2commons
    }
    url = url
    info = youtube_dl.YoutubeDL(params).extract_info(url, download=False)

    assert 'formats' in info, 'Your url cannot be processed correctly'

    ie_key = info['extractor_key']
    title = info.get('title', '').strip()
    uploader = escape_wikitext(info.get('uploader', '').strip())
    date = info.get('upload_date', '').strip()
    desc_orig = desc = info.get('description', '').strip() or title

    # Process date
    if re.match(r'^[0-9]{8}$', date):
        date = '%s-%s-%s' % (date[0:4], date[4:6], date[6:8])

    # Source
    if ie_key == 'Youtube' and info['id']:
        source = '{{From YouTube|1=%(id)s|2=%(title)s}}' % \
            {'id': info['id'], 'title': escape_wikitext(title)}
    elif ie_key == 'Vimeo' and info['id']:
        source = '{{From Vimeo|1=%(id)s|2=%(title)s}}' % \
            {'id': info['id'], 'title': escape_wikitext(title)}
    elif ie_key == 'Generic':
        source = url
    else:
        source = '[%(url)s %(title)s - %(extractor)s]' % \
            {'url': url, 'title': escape_wikitext(title), 'extractor': ie_key}

    # Description
    desc = escape_wikitext(desc)
    if len(desc_orig) > 100:
        lang = guess_language.guessLanguage(desc_orig)
        if lang != 'UNKNOWN':
            desc = u'{{' + lang + u'|1=' + desc + u'}}'

    # License
    lic = '{{subst:nld}}'
    uploader_param = '|%s' % uploader if uploader else ''
    if ie_key == 'Youtube' and info.get('license') == \
            'Creative Commons Attribution license (reuse allowed)':
        lic = '{{YouTube CC-BY%s}}' % uploader_param
    elif ie_key == 'Flickr':
        if info.get('license') == 'Attribution':
            lic = '{{cc-by-2.0%s}}' % uploader_param
        elif info.get('license') == 'Attribution-ShareAlike':
            lic = '{{cc-by-sa-2.0%s}}' % uploader_param
        elif info.get('license') == 'No known copyright restrictions':
            lic = '{{Flickr-no known copyright restrictions}}'
        elif info.get('license') == 'United States government work':
            lic = '{{PD-USGov}}'
        elif info.get('license') == 'Public Domain Dedication (CC0)':
            lic = '{{cc-zero}}'
        elif info.get('license') in \
                ['Public Domain Work', 'Public Domain Mark']:
            lic = '{{safesubst:Flickr-public domain mark/subst}}'

    # Author
    uploader_url = info.get('uploader_url', '')
    if uploader_url:
        uploader = u'[%s %s]' % (uploader_url, uploader)

    filedesc = """
=={{int:filedesc}}==
{{Information
|description=%(desc)s
|date=%(date)s
|source=%(source)s
|author=%(uploader)s
|permission=
|other_versions=
|other_fields=
}}

=={{int:license-header}}==
%(license)s
{{LicenseReview}}

[[Category:Uploaded with video2commons]]
""" % {
        'desc': desc,
        'date': date,
        'source': source,
        'uploader': uploader,
        'license': lic
    }

    return jsonify(
        url=url,
        extractor=ie_key,
        filedesc=filedesc.strip(),
        filename=title
    )


def escape_wikitext(wikitext):
    """Escape wikitext for use in file description."""
    rep = {
        '{|': '{{(!}}',
        '|}': '{{|}}',
        '||': '{{!!}}',
        '|': '{{!}}',
        '[[': '{{!((}}',
        ']]': '{{))!}',
        '{{': '{{((}}',
        '}}': '{{))}}',
        '{': '{{(}}',
        '}': '{{)}}',
    }
    rep = dict((re.escape(k), v) for k, v in rep.iteritems())
    pattern = re.compile("|".join(rep.keys()))
    return pattern.sub(lambda m: rep[re.escape(m.group(0))], wikitext)


@api.route('/listformats', methods=['POST'])
def list_formats():
    """List the possible convert formats from a given audio/video pair."""
    formats = []
    prefer = ''
    video = _boolize(request.form['video'])
    audio = _boolize(request.form['audio'])
    if not video and audio:
        raise RuntimeError('Eithor video or audio must be kept')
    elif video and not audio:
        formats = ['ogv (Theora)', 'webm (VP8)', 'webm (VP9, experimental)']
        prefer = 'webm (VP8)'
    elif not video and audio:
        formats = ['ogg (Vorbis)', 'opus (Opus, experimental)']
        prefer = 'ogg (Vorbis)'
    elif video and audio:
        formats = ['ogv (Theora/Vorbis)', 'webm (VP8/Vorbis)',
                   'webm (VP9/Opus, experimental)']
        prefer = 'webm (VP8/Vorbis)'

    return jsonify(
        format=prefer,
        formats=formats
    )


def _boolize(data):
    return data in [True, 'true', 'TRUE', 'True', 1, '1']


@api.route('/validatefilename', methods=['POST'])
def validate_filename():
    """Validate filename for invalid characters/parts."""
    return jsonify(
        filename=_validate_filename(request.form['filename'])
    )


def _validate_filename(filename):
    for char in '[]{}|#<>%+?!:/\\.':
        assert char not in filename, \
            'Your filename contains an illegal character: ' + char

    illegalords = range(0, 32) + [127]
    for char in filename:
        # ord(char) to prevent bad renderings
        assert ord(char) not in illegalords, \
            'Your filename contains an illegal character: chr(%d)' % ord(char)

    assert len(filename) < 250, 'Your filename is too long'

    assert not re.search(r"&[A-Za-z0-9\x80-\xff]+;", filename), \
        'Your filename contains XML/HTML character references'

    return filename.replace('_', ' ')


def get_download_key(format):
    """Get the youtube-dl download format key."""
    return {
        'ogv (Theora)': 'bestvideo/best',
        'webm (VP8)': 'bestvideo/best',
        'webm (VP9, experimental)': 'bestvideo/best',
        'ogg (Vorbis)': 'bestaudio/best',
        'opus (Opus, experimental)': 'bestaudio/best',
        'ogv (Theora/Vorbis)': 'bestvideo+bestaudio/best',
        'webm (VP8/Vorbis)': 'bestvideo+bestaudio/best',
        'webm (VP9/Opus, experimental)': 'bestvideo+bestaudio/best',
    }[format]


def get_convert_key(format):
    """Get the backend convert key from human-readable convert format."""
    return {
        'ogv (Theora)': 'an.ogv',
        'webm (VP8)': 'an.webm',
        'webm (VP9, experimental)': 'an.vp9.webm',
        'ogg (Vorbis)': 'ogg',
        'opus (Opus, experimental)': 'opus',
        'ogv (Theora/Vorbis)': 'ogv',
        'webm (VP8/Vorbis)': 'webm',
        'webm (VP9/Opus, experimental)': 'vp9.webm',
    }[format]


@api.route('/task/run', methods=['POST'])
def run_task():
    """Run a task with parameters from session."""
    url = request.form['url']
    ie_key = request.form['extractor']
    subtitles = request.form['subtitles']
    filename = request.form['filename']
    filedesc = request.form['filedesc']
    downloadkey = get_download_key(request.form['format'])
    convertkey = get_convert_key(request.form['format'])
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
    adminabort = False
    try:
        assert id in \
            redisconnection.lrange('tasks:' + username, 0, -1), \
            'Task must belong to you.'
    except AssertionError:
        if is_sudoer(username):
            adminabort = True
        else:
            raise
    worker.main.AsyncResult(id).abort()
    if adminabort:
        redisconnection.set('restarted:' + id, 'ADMINABORT')
    return jsonify(remove='success', id=id)
