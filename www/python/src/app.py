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

"""video2commons web frontend."""

import os
import sys
import re
import pickle
import traceback
import urllib

from flask import (
    Flask, request, session, render_template, redirect, url_for, jsonify
)
# https://github.com/mediawiki-utilities/python-mwoauth
from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
from requests_oauthlib import OAuth1
from config import consumer_key, consumer_secret, api_url, redis_pw, redis_host
from redis import Redis
from celery.result import AsyncResult
import youtube_dl
import guess_language

from redisession import RedisSessionInterface

sys.path.append(
    os.path.dirname(os.path.realpath(__file__)) + "/../../../backend/"
)

import worker  # NOQA

consumer_token = ConsumerToken(consumer_key, consumer_secret)
handshaker = Handshaker(api_url, consumer_token)

redisconnection = Redis(host=redis_host, db=3, password=redis_pw)

app = Flask(__name__)

app.session_interface = RedisSessionInterface(redisconnection)


@app.errorhandler(Exception)
def all_exception_handler(error):
    """Handle an exception and show the traceback to error page."""
    return 'Please notify [[commons:User:Zhuyifei1999]]: ' + \
        traceback.format_exc(), 500


def check_banned():
    """Check for banned cases."""
    # Check for WP0 traffic

    return None


@app.route('/')
def main():
    """Main page."""
    banned = check_banned()
    if banned:
        return render_template('banned.min.html', reason=banned)

    try:
        dologin()
    except:
        return render_template('main.min.html', loggedin=False)

    return render_template('main.min.html', loggedin=True)


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
    return OAuth1(
        client_key=consumer_token.key,
        client_secret=consumer_token.secret,
        resource_owner_key=access_token.key,
        resource_owner_secret=access_token.secret
    )


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
    session['access_token_key'], session['access_token_secret'] = \
        access_token.key, access_token.secret

    return redirect(url_for('main'))


@app.route('/logout')
def logout():
    """Logout: clear all session data."""
    session.clear()

    return redirect(url_for('main'))


# APIs
@app.route('/api/status')
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
        res = AsyncResult(id)
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
                elif isinstance(e, worker.upload.NeedServerSideUpload):
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

    return 'An exception occured: %s: %s' % \
        (type(e).__name__, desc)


def get_tasks():
    """Get a list of visible tasks for user."""
    # sudoer = able to monitor all tasks
    username = session['username']
    sudoers = redisconnection.lrange('sudoers', 0, -1)
    if username in sudoers:
        key = 'alltasks'
    else:
        key = 'tasks:' + username

    return redisconnection.lrange(key, 0, -1)[::-1]


def get_title_from_task(id):
    """Get task title from task ID."""
    return redisconnection.get('titles:' + id)


def create_phab_url(es):
    """Create a server side upload Phabricator URL."""
    wgetlinks = []

    for e in es:
        wgetlink = 'wget ' + e.url + '{,.txt}'
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


@app.route('/api/task/new', methods=['POST'])
def new_task():
    """Create a new task with variables prefilled."""
    if 'newtasks' not in session:
        session['newtasks'] = {}

    id = ""
    for i in range(10):  # 10 tries
        id = os.urandom(8).encode('hex')
        if id not in session['newtasks']:
            session['newtasks'][id] = {}
            break
    else:
        raise RuntimeError("Too many retries to generate a task id")

    session['newtasks'][id]['url'] = ""
    session['newtasks'][id]['extractor'] = ""
    session['newtasks'][id]['audio'] = True
    session['newtasks'][id]['video'] = True
    session['newtasks'][id]['subtitles'] = True
    session['newtasks'][id]['filename'] = ""
    session['newtasks'][id]['formats'] = []
    session['newtasks'][id]['format'] = ""
    session['newtasks'][id]['filedesc'] = ""

    return jsonify(
        id=id,
        step='source',
        url=session['newtasks'][id]['url'],
        audio=session['newtasks'][id]['audio'],
        video=session['newtasks'][id]['video'],
        subtitles=session['newtasks'][id]['subtitles']
    )


@app.route('/api/task/submit', methods=['POST'])
def submit_task():
    """Handle task parameters."""
    banned = check_banned()
    if banned:
        return jsonify(
            step='error',
            error='You are banned from using this tool! Reason: ' + banned
        )

    try:
        if 'newtasks' not in session:
            session['newtasks'] = {}

        # Asserts
        if 'id' not in request.form:
            return jsonify(
                step='error',
                error='Your submitted data cannot be parsed. Please try again.'
            )

        id = request.form['id']
        if id not in session['newtasks']:
            return jsonify(
                step='error',
                error='We could not process your data due to loss of ' +
                'session data. Please reload the page and try again.'
            )

        for data in [
            'url', 'extractor', 'audio', 'video', 'subtitles',
            'filename', 'format', 'formats', 'filedesc'
        ]:
            if data not in session['newtasks'][id]:
                return jsonify(
                    step='error',
                    error='We could not process your data due to loss of ' +
                    'session data. Please reload the page and try again.'
                )

        # Save current data
        step = request.form['step']
        if step == 'source':
            if not request.form['url'].strip():
                return jsonify(step='error', error='URL cannot be empty!')

            formaudio = request.form['audio'] in \
                [True, 'true', 'TRUE', 'True', 1, '1']
            formvideo = request.form['video'] in \
                [True, 'true', 'TRUE', 'True', 1, '1']
            formsubtitles = request.form['subtitles'] in \
                [True, 'true', 'TRUE', 'True', 1, '1']

            # re-extract url data via youtube-dl
            need_rextract = \
                request.form['url'].strip() != session['newtasks'][id]['url']
            session['newtasks'][id]['url'] = request.form['url'].strip()
            session['newtasks'][id]['audio'] = formaudio
            session['newtasks'][id]['video'] = formvideo
            session['newtasks'][id]['subtitles'] = formsubtitles

            if need_rextract:
                rextract_url(id)
            relist_formats(id)

        elif step == 'target':
            if request.form['format'].strip() not in \
                    session['newtasks'][id]['formats']:
                return jsonify(
                    step='error',
                    error='An invalid format was requested and could ' +
                    'not be processed. Please reload the dialog and try again.'
                )
            if not (
                request.form['filename'].strip() and
                request.form['filedesc'].strip()
            ):
                return jsonify(
                    step='error',
                    error='Filename and file description cannot be empty!'
                )

            session['newtasks'][id]['filename'] = \
                request.form['filename'].strip()
            session['newtasks'][id]['format'] = \
                request.form['format'].strip()
            session['newtasks'][id]['filedesc'] = \
                request.form['filedesc'].strip()

            revalidate_filename(id)

        elif step == 'confirm':
            pass  # nothing to do in confirm screen

        else:
            return jsonify(
                step='error',
                error='Something weird going on. ' +
                'Please notify [[commons:User:Zhuyifei1999]]'
            )

        action = request.form['action']
        if step == 'source' and action == 'prev':
            return jsonify(
                step='error',
                error='You cannot go to the previous step of first step.')
        elif step == 'confirm' and action == 'next':
            return run_task(id)

        # Send new data
        action = {'prev': -1, 'next': 1}[action]
        steps = ['source', 'target', 'confirm']
        step = steps[steps.index(step) + action]

        if step == 'source':
            return jsonify(
                id=id,
                step=step,
                url=session['newtasks'][id]['url'],
                audio=session['newtasks'][id]['audio'],
                video=session['newtasks'][id]['video'],
                subtitles=session['newtasks'][id]['subtitles']
            )
        elif step == 'target':
            return jsonify(
                id=id,
                step=step,
                filename=session['newtasks'][id]['filename'],
                formats=session['newtasks'][id]['formats'],
                format=session['newtasks'][id]['format'],
                filedesc=session['newtasks'][id]['filedesc']
            )
        elif step == 'confirm':
            keep = ", ".join(filter(None, [
                'video' if session['newtasks'][id]['video'] else False,
                'audio' if session['newtasks'][id]['audio'] else False,
                'subtitles' if session['newtasks'][id]['subtitles'] else False,
            ]))
            return jsonify(
                id=id,
                step=step,
                url=session['newtasks'][id]['url'],
                extractor=session['newtasks'][id]['extractor'],
                keep=keep,
                filename=session['newtasks'][id]['filename'],
                format=session['newtasks'][id]['format'],
                filedesc=session['newtasks'][id]['filedesc']
            )

    except Exception, e:
        session.rollback()
        return jsonify(
            step='error',
            error=format_exception(e),
            traceback=traceback.format_exc()
        )


def relist_formats(id):
    """List the possible convert formats from a given audio/video pair."""
    formats = []
    prefer = ''
    if not session['newtasks'][id]['video'] and \
            not session['newtasks'][id]['audio']:
        raise RuntimeError('Eithor video or audio must be kept')
    elif session['newtasks'][id]['video'] and \
            not session['newtasks'][id]['audio']:
        formats = ['ogv (Theora)', 'webm (VP8)', 'webm (VP9, experimental)']
        prefer = 'webm (VP8)'
    elif not session['newtasks'][id]['video'] and \
            session['newtasks'][id]['audio']:
        formats = ['ogg (Vorbis)', 'opus (Opus, experimental)']
        prefer = 'ogg (Vorbis)'
    elif session['newtasks'][id]['video'] and \
            session['newtasks'][id]['audio']:
        formats = ['ogv (Theora/Vorbis)', 'webm (VP8/Vorbis)',
                   'webm (VP9/Opus, experimental)']
        prefer = 'webm (VP8/Vorbis)'

    session['newtasks'][id]['format'] = prefer
    session['newtasks'][id]['formats'] = formats


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


def revalidate_filename(id):
    """Validate filename for invalid characters/parts."""
    filename = session['newtasks'][id]['filename']
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

    session['newtasks'][id]['filename'] = filename.replace('_', ' ')


def rextract_url(id):
    """Extract a video url."""
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
    url = session['newtasks'][id]['url']
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
    if ie_key == 'Youtube' and info.get('license') == \
            'Creative Commons Attribution license (reuse allowed)':
        if uploader:
            lic = '{{YouTube CC-BY|%s}}' % uploader
        else:
            lic = '{{YouTube CC-BY}}'

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
    session['newtasks'][id]['extractor'] = ie_key
    session['newtasks'][id]['filedesc'] = filedesc.strip()
    session['newtasks'][id]['filename'] = title


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


def run_task(id):
    """Run a task with parameters from session."""
    url = session['newtasks'][id]['url']
    ie_key = session['newtasks'][id]['extractor']
    subtitles = session['newtasks'][id]['subtitles']
    filename = session['newtasks'][id]['filename']
    filedesc = session['newtasks'][id]['filedesc']
    downloadkey = get_download_key(session['newtasks'][id]['format'])
    convertkey = get_convert_key(session['newtasks'][id]['format'])
    username = session['username']
    oauth = (session['access_token_key'], session['access_token_secret'])

    taskid = run_task_internal(filename, (
        url, ie_key, subtitles, filename, filedesc,
        downloadkey, convertkey, username, oauth
    ))

    del session['newtasks'][id]

    return jsonify(id=id, step='success', taskid=taskid)


def run_task_internal(filename, params):
    """Internal run task function to accept whatever params given."""
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


@app.route('/api/task/restart', methods=['POST'])
def restart_task():
    """Reastart a task: run a task with params of another task."""
    try:
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
    except Exception, e:
        session.rollback()
        return jsonify(
            restart='error',
            error=format_exception(e),
            traceback=traceback.format_exc()
        )


@app.route('/api/task/remove', methods=['POST'])
def remove_task():
    """Revove a task from list of tasks."""
    try:
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
    except Exception, e:
        session.rollback()
        return jsonify(
            remove='error',
            error=format_exception(e),
            traceback=traceback.format_exc()
        )

if __name__ == '__main__':
    app.run()
