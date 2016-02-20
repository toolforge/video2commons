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

import os, sys
import re
import pickle
import traceback

from flask import Flask, request, Response, session, render_template, redirect, url_for, jsonify
# https://github.com/mediawiki-utilities/python-mwoauth
from mwoauth import AccessToken, ConsumerToken, RequestToken, Handshaker
import requests
from requests_oauthlib import OAuth1
from config import consumer_key, consumer_secret, api_url, session_key, redis_pw, redis_host
from redis import Redis
from celery.result import AsyncResult
import youtube_dl

from redisession import RedisSessionInterface

sys.path.append(os.path.dirname(os.path.realpath(__file__))+"/../../../backend/")
import worker

consumer_token = ConsumerToken(consumer_key, consumer_secret)
handshaker = Handshaker(api_url, consumer_token)

redisconnection = Redis(host=redis_host, db=3, password=redis_pw)

app = Flask(__name__)

#app.secret_key = session_key
app.session_interface = RedisSessionInterface(redisconnection)


@app.errorhandler(Exception)
def all_exception_handler(error):
    return 'Please notify [[commons:User:Zhuyifei1999]]: ' + traceback.format_exc(), 500

@app.route('/')
def main():
    try:
        dologin()
    except:
        return render_template('bootstraphtml.html', loggedin=False)

    return render_template('bootstraphtml.html', loggedin=True)

def dologin():
    if not ('access_token_key' in session and 'access_token_secret' in session):
        raise NameError("No access keys")

    access_token = AccessToken(session['access_token_key'], session['access_token_secret'])
    #identity = 
    session['username'] = handshaker.identify(access_token)['username']
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
    session.clear()

    return redirect(url_for('main'))

# APIs
@app.route('/api/status')
def status():
    ids = getTasks()
    goodids = []
    values = []
    hasrunning = False
    for id in ids:
        title = getTitleFromTask(id)
        if not title: continue # task has been forgotten -- results should have been expired
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
                task['text'] = 'The status of the task could not be retrieved. It is presumably failed due to a failed chunk uploading and T124922.'
                task['traceback'] = traceback.format_exc()
        else:
            if res.state == 'PENDING':
                task['status'] = 'progress'
                task['text'] = 'Your task is pending...'
                task['progress'] = -1
                hasrunning = True
            elif res.state == 'STARTED':
                task['status'] = 'progress'
                task['text'] = 'Your task has been started; preprocessing...'
                task['progress'] = -1
                hasrunning = True
            elif res.state == 'PROGRESS':
                task['status'] = 'progress'
                task['text'] = res.result['text']
                task['progress'] = res.result['percent']
                hasrunning = True
            elif res.state == 'SUCCESS':
                task['status'] = 'done'
                filename, wikifileurl = res.result
                task['url'] = wikifileurl
                task['text'] = filename
            elif res.state == 'FAILURE':
                e = res.result
                if isinstance(e, worker.upload.NeedServerSideUpload):
                    task['status'] = 'needssu'
                    task['url'] = e.url
                else:
                    task['status'] = 'fail'
                    task['text'] = 'An exception occured: %s: %s' % (type(e).__name__, str(e))
                    task['restartable'] = (not redisconnection.exists('restarted:' + id)) and redisconnection.exists('params:' + id)
            else:
                task['status'] = 'fail'
                task['text'] = 'Something weird going on. Please notify [[commons:User:Zhuyifei1999]]'

        values.append(task)

    return jsonify(ids=goodids, values=values, hasrunning=hasrunning)

def getTasks():
    # sudoer = able to monitor all tasks
    username = session['username']
    sudoers = redisconnection.lrange('sudoers', 0, -1)
    if username in sudoers:
        key = 'alltasks'
    else:
        key = 'tasks:' + username

    return redisconnection.lrange(key, 0, -1)[::-1]

def getTitleFromTask(id):
    return redisconnection.get('titles:' + id)

@app.route('/api/task/new', methods=['POST'])
def newTask():
    if not 'newtasks' in session:
        session['newtasks'] = {}

    id = ""
    for i in range(10): # 10 tries
        id = os.urandom(8).encode('hex')
        if not id in session['newtasks']:
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
        id = id,
        step = 'source',
        url = session['newtasks'][id]['url'],
        audio = session['newtasks'][id]['audio'],
        video = session['newtasks'][id]['video'],
        subtitles = session['newtasks'][id]['subtitles']
    )

@app.route('/api/task/submit', methods=['POST'])
def submitTask():
    try:
        if not 'newtasks' in session:
            session['newtasks'] = {}

        # Asserts
        if not 'id' in request.form:
            return jsonify(step='error', error='Your submitted data cannot be parsed. Please try again.')

        id = request.form['id']
        if not id in session['newtasks']:
            return jsonify(step='error', error='We could not process your data due to loss of session data. Please reload the page and try again.')

        for data in ['url', 'extractor', 'audio', 'video', 'subtitles', 'filename', 'format', 'formats', 'filedesc']:
            if not data in session['newtasks'][id]:
                return jsonify(step='error', error='We could not process your data due to loss of session data. Please reload the page and try again.')

        # Save current data
        step = request.form['step']
        if step == 'source':
            if not request.form['url'].strip():
                return jsonify(step='error', error='URL cannot be empty!')

            formaudio = request.form['audio'] in [True, 'true', 'TRUE', 'True', 1, '1']
            formvideo = request.form['video'] in [True, 'true', 'TRUE', 'True', 1, '1']
            formsubtitles = request.form['subtitles'] in [True, 'true', 'TRUE', 'True', 1, '1']

            needRextract = request.form['url'].strip() != session['newtasks'][id]['url'] # re-extract url data via youtube-dl

            session['newtasks'][id]['url'] = request.form['url'].strip()
            session['newtasks'][id]['audio'] = formaudio
            session['newtasks'][id]['video'] = formvideo
            session['newtasks'][id]['subtitles'] = formsubtitles

            if needRextract:
                rextractURL(id)
            relistFormats(id)

        elif step == 'target':
            if not request.form['format'].strip() in session['newtasks'][id]['formats']:
                return jsonify(step='error', error='An invalid format was requested and could not be processed. Please reload the dialog and try again.')
            if not (request.form['filename'].strip() and request.form['filedesc'].strip()):
                return jsonify(step='error', error='Filename and file description cannot be empty!')

            session['newtasks'][id]['filename'] = request.form['filename'].strip()
            session['newtasks'][id]['format'] = request.form['format'].strip()
            session['newtasks'][id]['filedesc'] = request.form['filedesc'].strip()

            revalidateFilename(id)

        elif step == 'confirm':
            pass # nothing to do in confirm screen

        else:
            return jsonify(step='error', error='Something weird going on. Please notify [[commons:User:Zhuyifei1999]]')

        action = request.form['action']
        if step == 'source' and action == 'prev':
            return jsonify(step='error', error='You cannot go to the previous step of first step.')
        elif step == 'confirm' and action == 'next':
            return runTask(id)

        # Send new data
        action = {'prev': -1, 'next': 1}[action]
        steps = ['source', 'target', 'confirm']
        step = steps[steps.index(step)+action]

        if step == 'source':
            return jsonify(
                id = id,
                step = step, 
                url = session['newtasks'][id]['url'],
                audio = session['newtasks'][id]['audio'],
                video = session['newtasks'][id]['video'],
                subtitles = session['newtasks'][id]['subtitles']
            )
        elif step == 'target':
            return jsonify(
                id = id,
                step = step, 
                filename = session['newtasks'][id]['filename'],
                formats = session['newtasks'][id]['formats'],
                format = session['newtasks'][id]['format'],
                filedesc = session['newtasks'][id]['filedesc']
            )
        elif step == 'confirm':
            keep = ", ".join(filter(None, [
                'video' if session['newtasks'][id]['video'] else False,
                'audio' if session['newtasks'][id]['audio'] else False,
                'subtitles' if session['newtasks'][id]['subtitles'] else False,
            ]))
            return jsonify(
                id = id,
                step = step, 
                url = session['newtasks'][id]['url'],
                extractor = session['newtasks'][id]['extractor'],
                keep = keep,
                filename = session['newtasks'][id]['filename'],
                format = session['newtasks'][id]['format'],
                filedesc = session['newtasks'][id]['filedesc']
            )

    except Exception, e:
        return jsonify(step='error', error='An exception occured: %s: %s' % (type(e).__name__, str(e)), traceback=traceback.format_exc())

def relistFormats(id):
    formats = []
    prefer = ''
    if not session['newtasks'][id]['video'] and not session['newtasks'][id]['audio']:
        raise RuntimeError('Eithor video or audio must be kept')
    elif session['newtasks'][id]['video'] and not session['newtasks'][id]['audio']:
        formats = ['ogv (Theora)', 'webm (VP8)', 'webm (VP9, experimental)']
        prefer = 'webm (VP8)'
    elif not session['newtasks'][id]['video'] and session['newtasks'][id]['audio']:
        formats = ['ogg (Vorbis)', 'opus (Opus, experimental)']
        prefer = 'ogg (Vorbis)'
    elif session['newtasks'][id]['video'] and session['newtasks'][id]['audio']:
        formats = ['ogv (Theora/Vorbis)', 'webm (VP8/Vorbis)', 'webm (VP9/Opus, experimental)']
        prefer = 'webm (VP8/Vorbis)'

    session['newtasks'][id]['format'] = prefer
    session['newtasks'][id]['formats'] = formats

def getConvertKey(format):
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

def revalidateFilename(id):
    filename = session['newtasks'][id]['filename']
    for char in '[]{}|#<>%+?!:/\\.':
        assert char not in filename, 'Your filename contains an illegal character: ' + char

    illegalords = range(0, 32) + [127]
    for char in filename:
        assert ord(char) not in illegalords, 'Your filename contains an illegal character: chr(%d)' % ord(char) # prevent bad renderings

    assert not re.search(r"&[A-Za-z0-9\x80-\xff]+;", filename), 'Your filename contains XML/HTML character references'

    session['newtasks'][id]['filename'] = filename.replace('_', ' ')

def rextractURL(id):
    params = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': '/dev/null',
        'writedescription': True,
        'writeinfojson': True,
        'writesubtitles': False,
        'subtitlesformat': 'srt/ass/vtt/best',
        'cachedir': '/tmp/',
        'noplaylist': True, # not implemented in video2commons
    }
    url = session['newtasks'][id]['url']
    info = youtube_dl.YoutubeDL(params).extract_info(url, download=False)

    assert 'formats' in info, 'Your url cannot be processed correctly'

    ie_key = info['extractor_key']
    title = info.get('title', '').strip()
    uploader = info.get('uploader', '').strip()
    date = info.get('upload_date', '').strip()
    desc = info.get('description', '').strip()

    # Process date
    if re.match(r'^[0-9]{8}$', date):
        date = '%s-%s-%s' % (date[0:4], date[4:6], date[6:8])

    # Source
    if ie_key == 'Youtube' and info['id']:
        source = '{{From YouTube|1=%(id)s|2=%(title)s}}' % {'id': info['id'], 'title': escapeWikitext(title)}
    elif ie_key == 'Vimeo' and info['id']:
        source = '{{From Vimeo|1=%(id)s|2=%(title)s}}' % {'id': info['id'], 'title': escapeWikitext(title)}
    elif ie_key == 'Generic':
        source = url
    else:
        source = '[%(url)s %(title)s - %(extractor)s]' % {'url': url, 'title': escapeWikitext(title), 'extractor': ie_key}

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
{{subst:nld}}

[[Category:Uploaded with video2commons]]
""" % {
        'desc': escapeWikitext(desc or title),
        'date': date,
        'source': source,
        'uploader': escapeWikitext(uploader)
    }
    session['newtasks'][id]['extractor'] = ie_key
    session['newtasks'][id]['filedesc'] = filedesc.strip()
    session['newtasks'][id]['filename'] = title

def escapeWikitext(wikitext):
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

def runTask(id):
    url = session['newtasks'][id]['url']
    ie_key = session['newtasks'][id]['extractor']
    subtitles = session['newtasks'][id]['subtitles']
    filename = session['newtasks'][id]['filename']
    filedesc = session['newtasks'][id]['filedesc']
    convertkey = getConvertKey(session['newtasks'][id]['format'])
    username = session['username']
    oauth = (session['access_token_key'], session['access_token_secret'])

    taskid = runTaskInternal(url, ie_key, subtitles, filename, filedesc, convertkey, username, oauth)

    del session['newtasks'][id]

    return jsonify(id = id, step = 'success', taskid = taskid)

def runTaskInternal(*params):
    res = worker.main.delay(*params)
    taskid = res.id

    expire = 2 * 30 * 24 * 3600 # 2 months
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
def restartTask():
    try:
        id = request.form['id']

        assert redisconnection.exists('titles:' + id), 'Task does not exist'
        assert id in redisconnection.lrange('tasks:' + session['username'], 0, -1), 'Task must belong to you.'

        restarted = redisconnection.get('restarted:' + id)
        assert not restarted, 'Task has already been restarted with id ' + restarted
        params = redisconnection.get('params:' + id)
        assert params, 'Could not extract the task parameters.'

        newid = runTaskInternal(*pickle.loads(params))
        redisconnection.set('restarted:' + id, newid)

        return jsonify(restart = 'success', id = newid)
    except Exception, e:
        return jsonify(restart='error', error='An exception occured: %s: %s' % (type(e).__name__, str(e)), traceback=traceback.format_exc())

@app.route('/api/task/remove', methods=['POST'])
def removeTask():
    try:
        id = request.form['id']
        username = session['username']
        redisconnection.lrem('alltasks', id) # not StrictRedis
        redisconnection.lrem('tasks:' + username, id) # not StrictRedis
        redisconnection.delete('titles:' + id)
        redisconnection.delete('params:' + id)
        redisconnection.delete('restarted:' + id)
        return jsonify(remove = 'success', id = id)
    except Exception, e:
        return jsonify(remove='error', error='An exception occured: %s: %s' % (type(e).__name__, str(e)), traceback=traceback.format_exc())

if __name__ == '__main__':
    app.run()
