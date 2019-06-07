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
# along with this program.  If not, see <https://www.gnu.org/licenses/>`
#

"""video2commons url extracter."""

from collections import OrderedDict
import re

import emoji
import guess_language
import pywikibot
import youtube_dl

SITE = pywikibot.Site()

# File extensions are probably alphanumeric with 0 to 4 chars
RE_EXTENSION = re.compile(r'^[a-z0-9]{0,4}$', re.IGNORECASE)

DEFAULT_LICENSE = '{{subst:nld|<!--replace this template with the license-->}}'
FILEDESC_TEMPLATE = """
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
"""


def make_dummy_desc(filename):
    filedesc = FILEDESC_TEMPLATE % {
        'desc': '',
        'date': '',
        'source': '',
        'uploader': '',
        'license': DEFAULT_LICENSE
    }

    # Remove the extension
    filename = filename.rsplit('.', 1)
    if len(filename) == 1 or RE_EXTENSION.match(filename[1]):
        filename = filename[0]
    else:
        filename = '.'.join(filename)

    return {
        'extractor': '(uploads)',
        'filedesc': filedesc.strip(),
        'filename': sanitize(filename)
    }


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

    assert 'formats' in info or info.get('direct'), \
        'Your url cannot be processed correctly'

    ie_key = info['extractor_key']
    title = (info.get('title') or '').strip()
    url = info.get('webpage_url') or url

    filedesc = FILEDESC_TEMPLATE % {
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
        'filename': sanitize(title)
    }


def _date(url, ie_key, title, info):
    date = (info.get('upload_date') or '').strip()
    if re.match(r'^[0-9]{8}$', date):
        date = '%s-%s-%s' % (date[0:4], date[4:6], date[6:8])
    return date


def _source(url, ie_key, title, info):
    if info['id']:
        if ie_key == 'Youtube':
            return '{{From YouTube|1=%(id)s|2=%(title)s}}' % \
                {'id': info['id'], 'title': escape_wikitext(title)}
        elif ie_key == 'Vimeo':
            return '{{From Vimeo|1=%(id)s|2=%(title)s}}' % \
                {'id': info['id'], 'title': escape_wikitext(title)}

    if ie_key == 'Generic':
        return url
    else:
        return '[%(url)s %(title)s - %(extractor)s]' % \
            {'url': url, 'title': escape_wikitext(title), 'extractor': ie_key}


def _desc(url, ie_key, title, info):
    desc_orig = desc = (info.get('description') or '').strip() or title
    desc = escape_wikitext(desc)
    if len(desc_orig) > 100:
        lang = guess_language.guessLanguage(desc_orig)
        if lang != 'UNKNOWN':
            desc = u'{{' + lang + u'|1=' + desc + u'}}'
    return desc


def _uploader(url, ie_key, title, info):
    uploader = escape_wikitext((info.get('uploader') or '').strip())
    uploader_url = info.get('uploader_url') or ''
    if uploader_url:
        # HACK: YouTube outputs http:// atm (issue #80)
        if ie_key == 'Youtube':
            uploader_url = uploader_url.replace('http://', 'https://')
        uploader = u'[%s %s]' % (uploader_url, uploader)
    return uploader


def _license(url, ie_key, title, info):
    uploader = info.get('uploader')
    uploader_param = ''
    if uploader:
        uploader_param = '|' + escape_wikitext(uploader.strip())

    default = DEFAULT_LICENSE
    if ie_key == 'Youtube' and info.get('license') == \
            'Creative Commons Attribution license (reuse allowed)':
        return '{{YouTube CC-BY%s}}' % uploader_param
    elif ie_key == 'Flickr':
        return {
            'Attribution':
                '{{cc-by-2.0%s}}' % uploader_param,
            'Attribution-ShareAlike':
                '{{cc-by-sa-2.0%s}}' % uploader_param,
            'No known copyright restrictions':
                '{{Flickr-no known copyright restrictions}}',
            'United States government work':
                '{{PD-USGov}}',
            'Public Domain Dedication (CC0)':
                '{{cc-zero}}',
            'Public Domain Work':
                '{{safesubst:Flickr-public domain mark/subst}}',
            'Public Domain Mark':
                '{{safesubst:Flickr-public domain mark/subst}}',
        }.get(info.get('license'), default)
    elif ie_key == 'Vimeo':
        return {
            'by':
                '{{cc-by-3.0%s}}' % uploader_param,
            'by-sa':
                '{{cc-by-sa-3.0%s}}' % uploader_param,
            'cc0':
                '{{cc-zero}}',
        }.get(info.get('license'), default)

    return default


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


# Source: mediawiki.Title.js@9df363d
sanitationRules = [
    # issue #101
    {
        'pattern': emoji.get_emoji_regexp(),
        'replace': ''
    },
    # "signature"
    {
        'pattern': re.compile(ur'~{3}'),
        'replace': ''
    },
    # Space, underscore, tab, NBSP and other unusual spaces
    {
        'pattern': re.compile(ur'[ _\u0009\u00A0\u1680\u180E\u2000-\u200A'
                              ur'\u2028\u2029\u202F\u205F\u3000\s]+'),
        'replace': ' '
    },
    # issue #96
    {
        'pattern': re.compile(ur'\u200B'),
        'replace': ''
    },
    # unicode bidi override characters: Implicit, Embeds, Overrides
    {
        'pattern': re.compile(ur'[\u200E\u200F\u202A-\u202E]'),
        'replace': ''
    },
    # control characters
    {
        'pattern': re.compile(ur'[\x00-\x1f\x7f]'),
        'replace': ''
    },
    # URL encoding (possibly)
    {
        'pattern': re.compile(ur'%([0-9A-Fa-f]{2})'),
        'replace': r'% \1'
    },
    # HTML-character-entities
    {
        'pattern': re.compile(ur'&(([A-Za-z0-9\x80-\xff]+|'
                              ur'#[0-9]+|#x[0-9A-Fa-f]+);)'),
        'replace': r'& \1'
    },
    # slash, colon (not supported by file systems like NTFS/Windows,
    # Mac OS 9 [:], ext4 [/])
    {
        'pattern': re.compile(ur'[:/#]'),
        'replace': '-'
    },
    # brackets, greater than
    {
        'pattern': re.compile(ur'[\]\}>]'),
        'replace': ')'
    },
    # brackets, lower than
    {
        'pattern': re.compile(ur'[\[\{<]'),
        'replace': '('
    },
    # directory structures
    {
        'pattern': re.compile(ur'^(\.|\.\.|\./.*|\.\./.*|.*/\./.*|'
                              ur'.*/\.\./.*|.*/\.|.*/\.\.)$'),
        'replace': ''
    },
    # everything that wasn't covered yet
    {
        'pattern': re.compile(ur'[|#+?:/\\\u0000-\u001f\u007f]'),
        'replace': '-'
    },
    # titleblacklist-custom-double-apostrophe
    {
        'pattern': re.compile(ur"'{2,}"),
        'replace': '"'
    },
]


def sanitize(filename):
    """Sanitize a filename for uploading."""
    for rule in sanitationRules:
        filename = rule['pattern'].sub(rule['replace'], filename)

    return filename


def do_validate_filename(filename):
    """Validate filename for invalid characters/parts."""
    assert len(filename) < 250, 'Your filename is too long'

    for rule in sanitationRules:
        reobj = rule['pattern'].search(filename)
        assert not reobj or reobj.group(0) == ' ', \
            'Your filename contains an illegal part: %r' % reobj.group(0)

    return filename.replace('_', ' ')


def do_validate_filedesc(filedesc):
    """Validate filename for invalid characters/parts."""
    parse = SITE._simple_request(
        action='parse',
        text=filedesc,
        prop='externallinks'
    ).submit()

    externallinks = parse.get('parse', {}).get('externallinks', [])

    if externallinks:
        spam = SITE._simple_request(
            action='spamblacklist',
            url=externallinks
        ).submit()

        assert spam.get('spamblacklist', {}).get('result') != 'blacklisted', \
            ('Your file description matches spam blacklist! Matches: %s' %
             ', '.join(spam.get('spamblacklist', {}).get('matches', [])))

    return filedesc
