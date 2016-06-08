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

"""video2commons url extracter."""

import re
from collections import OrderedDict

import youtube_dl
import guess_language


def do_extract_url(url):
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
    info = youtube_dl.YoutubeDL(params).extract_info(url, download=False)

    assert 'formats' in info, 'Your url cannot be processed correctly'

    ie_key = info['extractor_key']
    title = info.get('title', '').strip()

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
        'desc': _desc(url, ie_key, title, info),
        'date': _date(url, ie_key, title, info),
        'source': _source(url, ie_key, title, info),
        'uploader': _uploader(url, ie_key, title, info),
        'license': _license(url, ie_key, title, info)
    }

    return {
        'url': url,
        'extractor': ie_key,
        'filedesc': filedesc.strip(),
        'filename': title
    }


def _date(url, ie_key, title, info):
    date = info.get('upload_date', '').strip()
    if re.match(r'^[0-9]{8}$', date):
        date = '%s-%s-%s' % (date[0:4], date[4:6], date[6:8])
    return date


def _source(url, ie_key, title, info):
    if ie_key == 'Youtube' and info['id']:
        return '{{From YouTube|1=%(id)s|2=%(title)s}}' % \
            {'id': info['id'], 'title': escape_wikitext(title)}
    elif ie_key == 'Vimeo' and info['id']:
        return '{{From Vimeo|1=%(id)s|2=%(title)s}}' % \
            {'id': info['id'], 'title': escape_wikitext(title)}
    elif ie_key == 'Generic':
        return url
    else:
        return '[%(url)s %(title)s - %(extractor)s]' % \
            {'url': url, 'title': escape_wikitext(title), 'extractor': ie_key}


def _desc(url, ie_key, title, info):
    desc_orig = desc = info.get('description', '').strip() or title
    desc = escape_wikitext(desc)
    if len(desc_orig) > 100:
        lang = guess_language.guessLanguage(desc_orig)
        if lang != 'UNKNOWN':
            desc = u'{{' + lang + u'|1=' + desc + u'}}'
    return desc


def _uploader(url, ie_key, title, info):
    uploader = escape_wikitext(info.get('uploader', '').strip())
    uploader_url = info.get('uploader_url', '')
    if uploader_url:
        uploader = u'[%s %s]' % (uploader_url, uploader)
    return uploader


def _license(url, ie_key, title, info):
    uploader_param = '|' + escape_wikitext(info.get('uploader', '').strip()) \
        if 'uploader' in info else ''

    if ie_key == 'Youtube' and info.get('license') == \
            'Creative Commons Attribution license (reuse allowed)':
        return '{{YouTube CC-BY%s}}' % uploader_param
    elif ie_key == 'Flickr':
        if info.get('license') == 'Attribution':
            return '{{cc-by-2.0%s}}' % uploader_param
        elif info.get('license') == 'Attribution-ShareAlike':
            return '{{cc-by-sa-2.0%s}}' % uploader_param
        elif info.get('license') == 'No known copyright restrictions':
            return '{{Flickr-no known copyright restrictions}}'
        elif info.get('license') == 'United States government work':
            return '{{PD-USGov}}'
        elif info.get('license') == 'Public Domain Dedication (CC0)':
            return '{{cc-zero}}'
        elif info.get('license') in \
                ['Public Domain Work', 'Public Domain Mark']:
            return '{{safesubst:Flickr-public domain mark/subst}}'

    return '{{subst:nld}}'


def escape_wikitext(wikitext):
    """Escape wikitext for use in file description."""
    rep = OrderedDict([
        ('{|', '{{(!}}'),
        ('|}', '{{|}}'),
        ('||', '{{!!}}'),
        ('|', '{{!}}'),
        ('[[', '{{!((}}'),
        (']]', '{{))!}'),
        ('{{', '{{((}}'),
        ('}}', '{{))}}'),
        ('{', '{{(}}'),
        ('}', '{{)}}'),
    ])
    rep = dict((re.escape(k), v) for k, v in rep.iteritems())
    pattern = re.compile("|".join(rep.keys()))
    return pattern.sub(lambda m: rep[re.escape(m.group(0))], wikitext)
