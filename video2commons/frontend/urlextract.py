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

import json
import re
import subprocess
from collections import OrderedDict

import emoji
import guess_language
import pywikibot
import yt_dlp

from video2commons.backend.encode.transcode import WebVideoTranscode
from video2commons.frontend.shared import redisconnection
from video2commons.frontend.wcqs import WcqsSession
from video2commons.shared.ratelimiting import YoutubeDLRateLimited
from video2commons.shared.yt_dlp import add_youtube_params

SITE = pywikibot.Site()

# File extensions are probably alphanumeric with 0 to 4 chars
RE_EXTENSION = re.compile(r"^[a-z0-9]{0,4}$", re.IGNORECASE)

DEFAULT_LICENSE = "{{subst:nld|<!--replace this template with the license-->}}"
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

NAMESPACE_FILE = 6

# The fields of the yt-dlp metadata that the description uses, besides
# extractor_key and webpage_url. Those with a format are inserted as is in the
# description; the others are escaped, or only compared with known values.
RE_INFO_EXTRACTOR_KEY = re.compile(r"[A-Za-z0-9]+")
RE_INFO_URL = re.compile(r"https?://[^\s\[\]{}|<>\"]+")
INFO_FIELDS = {
    "id": re.compile(r"[A-Za-z0-9_.-]+"),
    "extractor": None,
    "title": None,
    "description": None,
    "uploader": None,
    "uploader_url": RE_INFO_URL,
    "upload_date": re.compile(r"[0-9]{8}"),
    "license": None,
}
MAX_INFO_FIELD_LENGTH = 20000

# Upload filenames are limited to 228 bytes (not counting the extension).
#
# This number was chosen since the length of the longest output extension we
# support is 12 bytes long, and 228 + 12 = 240, which is the maximum filename
# size supported by MediaWiki for uploads.
MAX_FILENAME_SIZE = 228

# Task queue routing thresholds for the default and heavy queues. Both 4k and
# 20 Mbps (in kbps) videos get routed to the heavy queue to avoid OOM errors.
HEAVY_RESOLUTION_THRESHOLD = 3840
HEAVY_BITRATE_THRESHOLD = 20000
DEFAULT_QUEUE = "celery"
HEAVY_QUEUE = "heavy"

# The frontend has a shorter timeout for ratelimiting because it only fetches
# metadata. Metadata should always be returnable within a minute, so the lock
# shouldn't be held for too long so URL extractions don't hang for too long.
RATELIMIT_LOCK_TIMEOUT = 60

# The frontend only extracts metadata (download=False), so extraction request
# sleeps can be shorter than the default used by the workers.
RATELIMIT_SLEEP_INTERVAL_REQUESTS = 1

REDIS_PREFIX_BLACKLIST_KEY = "commons:filename-prefix-blacklist"
REDIS_PREFIX_BLACKLIST_TTL = 24 * 3600  # 1 day


def predict_task_type(metadata):
    """Predict how resource-intensive a task is based on yt-dlp metadata."""
    # Check if the resolution exceed the threshold for the standard queue.
    width = metadata.get("width") or 0
    height = metadata.get("height") or 0
    if width >= HEAVY_RESOLUTION_THRESHOLD or height >= HEAVY_RESOLUTION_THRESHOLD:
        return HEAVY_QUEUE

    # Check the bitrate. TBR is total, VBR is video only (both in kbps).
    bitrate = metadata.get("tbr") or metadata.get("vbr") or 0
    if bitrate >= HEAVY_BITRATE_THRESHOLD:
        return HEAVY_QUEUE

    # Default to heavy if no bitrate is available. This is a fallback for video
    # sources that don't have yt-dlp extractors such as NASA Scientific
    # Visualization Studio, which typically has large files.
    if metadata.get("tbr") is None and metadata.get("vbr") is None:
        return HEAVY_QUEUE

    return DEFAULT_QUEUE


def predict_task_type_ffprobe(filepath):
    """Predict how resource-intensive a task is based on ffprobe metadata."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            filepath,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return DEFAULT_QUEUE

    probe = json.loads(result.stdout)

    # Check video streams for resolution.
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width") or 0
            height = stream.get("height") or 0
            if (
                width >= HEAVY_RESOLUTION_THRESHOLD
                or height >= HEAVY_RESOLUTION_THRESHOLD
            ):
                return HEAVY_QUEUE

    # Check bitrate from format (in bits/sec, convert to kbps).
    format_info = probe.get("format", {})
    bitrate_bps = int(format_info.get("bit_rate") or 0)
    bitrate_kbps = bitrate_bps / 1000
    if bitrate_kbps >= HEAVY_BITRATE_THRESHOLD:
        return HEAVY_QUEUE

    return DEFAULT_QUEUE


def make_dummy_desc(filename):
    filedesc = FILEDESC_TEMPLATE % {
        "desc": "",
        "date": "",
        "source": "",
        "uploader": "",
        "license": DEFAULT_LICENSE,
    }

    # Remove the extension
    filename = filename.rsplit(".", 1)
    if len(filename) == 1 or RE_EXTENSION.match(filename[1]):
        filename = filename[0]
    else:
        filename = ".".join(filename)

    return {
        "extractor": "(uploads)",
        "filedesc": filedesc.strip(),
        "filename": sanitize(filename),
    }


def make_info_desc(filename, info):
    """Create the description of an uploaded file from its yt-dlp metadata.

    This is the .info.json file that yt-dlp writes with --write-info-json, for
    a video that the user downloaded themselves, after clean_info(). The
    description is the one of the URL, without the server reaching the site.
    """
    desc = _extract_info(info)

    return {
        "extractor": "(uploads)",
        "filedesc": desc["filedesc"],
        "filename": desc["filename"] or make_dummy_desc(filename)["filename"],
    }


def clean_info(info):
    """Keep the valid fields of the yt-dlp metadata of a single video.

    The metadata comes from the user, like the rest of a manual upload, and
    the user can edit the description anyway. The fields are only checked so
    that the description is well-formed: a field that has the wrong type or
    format is left out, as yt-dlp does with the fields that a site doesn't have.
    """
    assert isinstance(info, dict), "The metadata file must contain a JSON object"
    assert info.get("_type") in (None, "video"), (
        "The metadata file must describe a single video, not a playlist"
    )

    extractor_key = info.get("extractor_key")
    assert _is_valid_info_field(extractor_key, RE_INFO_EXTRACTOR_KEY), (
        "The metadata file has no valid extractor_key: "
        "is it an .info.json file written by yt-dlp?"
    )
    url = info.get("webpage_url")
    assert _is_valid_info_field(url, RE_INFO_URL), (
        "The metadata file has no valid webpage_url"
    )

    cleaned = {
        "formats": [],
        "extractor_key": extractor_key,
        "webpage_url": url,
    }
    for field, regex in INFO_FIELDS.items():
        value = info.get(field)
        cleaned[field] = value if _is_valid_info_field(value, regex) else ""

    # The source of the description names the site of a sub-extractor (e.g.
    # "vimeo:album") from this name, but a site doesn't need one.
    cleaned["extractor"] = cleaned["extractor"] or extractor_key

    return cleaned


def _is_valid_info_field(value, regex):
    return (
        isinstance(value, str)
        and len(value) <= MAX_INFO_FIELD_LENGTH
        and (regex is None or regex.fullmatch(value) is not None)
    )


def do_extract_url(url):
    """Extract a video url."""
    params = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "/dev/null",
        "writedescription": True,
        "writeinfojson": True,
        "writesubtitles": False,
        "subtitlesformat": "srt/ass/vtt/best",
        "cachedir": "/tmp/",
        "noplaylist": False,
        "sleep_interval_requests": RATELIMIT_SLEEP_INTERVAL_REQUESTS,
    }

    if ".youtube.com/" in url:
        # https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies
        # https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp
        params = add_youtube_params(params)

        # Workaround: Ignore errors for YouTube playlists as yt-dlp will fail
        # if any of the videos in the playlist are marked as private or are
        # otherwise unavailable. We'd rather skip over those than fail.
        if "/playlist" in url or re.search(r"[?&]list=", url):
            params["ignoreerrors"] = True

    with YoutubeDLRateLimited(
        conn=redisconnection,
        source="frontend",
        url=url,
        params=params,
        timeout=RATELIMIT_LOCK_TIMEOUT,
        blocking_timeout=RATELIMIT_LOCK_TIMEOUT,
    ) as dl:
        info = dl.extract_info(url, download=False)

    # Extract playlist entries if this is a playlist.
    if info and "entries" in info:
        videos = []
        for entry in info["entries"]:
            if entry is None:
                continue  # Skip over videos that are unavailable.

            video_info = _extract_info(entry)
            videos.append(video_info)

        return {
            "type": "playlist",
            "id": info.get("id", ""),
            "title": info.get("title", ""),
            "url": url,
            "videos": videos,
        }

    video_info = _extract_info(info)

    return {"type": "single", **video_info}


def _extract_info(info):
    """Process metadata for a single video."""
    assert "formats" in info or info.get("direct"), (
        "Your url cannot be processed correctly"
    )

    ie_key = info["extractor_key"]
    title = (info.get("title") or "").strip()
    url = info.get("webpage_url")

    filedesc = FILEDESC_TEMPLATE % {
        "desc": _desc(url, ie_key, title, info),
        "date": _date(info),
        "source": _source(url, ie_key, title, info),
        "uploader": _uploader(url, ie_key, title, info),
        "license": _license(url, ie_key, title, info),
    }

    return {
        "url": url,
        "extractor": ie_key,
        "filedesc": filedesc.strip(),
        "filename": sanitize(title),
        "date": _date(info),
        "license": _normalize_license(ie_key, info),
        "queue": predict_task_type(info),
    }


def _date(info):
    date = (info.get("upload_date") or "").strip()
    if re.match(r"^[0-9]{8}$", date):
        date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
    return date


def _source(url, ie_key, title, info):
    if info["id"]:
        if ie_key == "Youtube":
            return "{{{{From YouTube|1={id}|2={title}}}}}".format(
                id=info["id"],
                title=escape_wikitext(title),
            )
        elif ie_key == "Vimeo":
            return "{{{{From Vimeo|1={id}|2={title}}}}}".format(
                id=info["id"],
                title=escape_wikitext(title),
            )

    if ie_key == "Generic":
        return url
    else:
        if ":" in info["extractor"]:
            # Try to find the anme of the 'owner' of this sub-ie
            ie_tmp = info["extractor"][: info["extractor"].index(":")]
            for ie in yt_dlp.gen_extractors():
                if ie.IE_NAME == ie_tmp:
                    ie_key = ie.ie_key()
                    break
        return f"[{url} {escape_wikitext(title)} - {ie_key}]"


def _desc(url, ie_key, title, info):
    desc_orig = desc = (info.get("description") or "").strip() or title
    desc = escape_wikitext(desc)
    if len(desc_orig) > 100:
        lang = guess_language.guess_language(desc_orig)
        if lang != "UNKNOWN":
            desc = "{{" + lang + "|1=" + desc + "}}"
    return desc


def _uploader(url, ie_key, title, info):
    uploader = escape_wikitext((info.get("uploader") or "").strip())
    uploader_url = info.get("uploader_url") or ""
    if uploader_url:
        # HACK: YouTube outputs http:// atm (issue #80)
        if ie_key == "Youtube":
            uploader_url = uploader_url.replace("http://", "https://")
        uploader = f"[{uploader_url} {uploader}]"
    return uploader


def _license(url, ie_key, title, info):
    """
    License template for Commons file description.
    """
    uploader = info.get("uploader")
    uploader_param = ""
    if uploader:
        uploader_param = "|" + escape_wikitext(uploader.strip())

    default = DEFAULT_LICENSE
    if (
        ie_key == "Youtube"
        and info.get("license")
        == "Creative Commons Attribution license (reuse allowed)"
    ):
        if _date(info) <= "2025-08-01":
            return f"{{{{YouTube CC-BY{uploader_param}}}}}"
        return f"{{{{YouTube CC-BY 4.0{uploader_param}}}}}"
    elif ie_key == "Flickr":
        # https://blog.flickr.net/en/2025/06/18/creative-commons-4-0-has-arrived-on-flickr/
        version = "2.0" if _date(info) <= "2025-06-18" else "4.0"

        return {
            "Attribution": f"{{{{cc-by-{version}{uploader_param}}}}}",
            "Attribution-ShareAlike": f"{{{{cc-by-sa-{version}{uploader_param}}}}}",
            "No known copyright restrictions": "{{Flickr-no known copyright restrictions}}",
            "United States government work": "{{PD-USGov}}",
            "Public Domain Dedication (CC0)": "{{cc-zero}}",
            "Public Domain Work": "{{safesubst:Flickr-public domain mark/subst}}",
            "Public Domain Mark": "{{safesubst:Flickr-public domain mark/subst}}",
        }.get(info.get("license"), default)
    elif ie_key == "Vimeo":
        return {
            "by": f"{{{{cc-by-3.0{uploader_param}}}}}",
            "by-sa": f"{{{{cc-by-sa-3.0{uploader_param}}}}}",
            "cc0": "{{cc-zero}}",
        }.get(info.get("license"), default)
    elif ie_key == "PeerTube":
        return {
            "Attribution": f"{{{{cc-by-4.0{uploader_param}}}}}",
            "CC BY 4.0": f"{{{{cc-by-4.0{uploader_param}}}}}",
            "Attribution - Share Alike": f"{{{{cc-by-sa-4.0{uploader_param}}}}}",
            "CC BY-SA 4.0": f"{{{{cc-by-sa-4.0{uploader_param}}}}}",
            "Public Domain Dedication": "{{cc-zero}}",
            "CC0 1.0": "{{cc-zero}}",
        }.get(info.get("license"), default)

    return default


def _normalize_license(ie_key, info) -> str | None:
    """Normalize license names to be more consistent across sources."""
    license_name = str(info.get("license") or "").strip()
    if not license_name:
        return None

    # Attempt to normalize the license name across common sources by checking
    # against ie_key and other identifiers.
    if (
        ie_key == "Youtube"
        and license_name == "Creative Commons Attribution license (reuse allowed)"
    ):
        return "CC-BY 3.0" if _date(info) <= "2025-08-01" else "CC-BY 4.0"
    elif ie_key == "Flickr":
        # https://blog.flickr.net/en/2025/06/18/creative-commons-4-0-has-arrived-on-flickr/
        version = "2.0" if _date(info) <= "2025-06-18" else "4.0"

        return {
            "Attribution": f"CC-BY-{version}",
            "Attribution-ShareAlike": f"CC-BY-SA-{version}",
            "United States government work": "PD-USGov",
            "Public Domain Dedication (CC0)": "CC-Zero",
        }.get(license_name, license_name)
    elif ie_key == "Vimeo":
        return {
            "by": "CC-BY-3.0",
            "by-sa": "CC-BY-SA-3.0",
            "cc0": "CC-Zero",
        }.get(license_name, license_name)
    elif ie_key == "PeerTube":
        return {
            "Attribution": "CC-BY-4.0",
            "Attribution - Share Alike": "CC-BY-SA-4.0",
            "Public Domain Dedication": "CC-Zero",
        }.get(license_name, license_name)

    # Fallback to the original license name if we can't normalize it.
    return license_name


def escape_wikitext(wikitext):
    """Escape wikitext for use in file description."""
    rep = OrderedDict(
        [
            ("{|", "{{(}}&#124;"),
            ("|}", "&#124;{{)}}"),
            ("||", "&#124;&#124;"),
            ("|", "&#124;"),
            ("[[", "{{!((}}"),
            ("]]", "{{))!}}"),
            ("[", "&#91;"),
            ("]", "&#93;"),
            ("{{", "{{((}}"),
            ("}}", "{{))}}"),
            ("{", "{{(}}"),
            ("}", "{{)}}"),
        ]
    )
    rep = {re.escape(k): v for k, v in rep.items()}
    pattern = re.compile("|".join(list(rep.keys())))
    return pattern.sub(lambda m: rep[re.escape(m.group(0))], wikitext)


def get_emoji_regexp():
    # Sort emoji by length to make sure multi-character emojis are
    # matched first
    emojis = sorted(emoji.EMOJI_DATA, key=len, reverse=True)
    pattern = "(" + "|".join(re.escape(u) for u in emojis) + ")"
    return re.compile(pattern)


# Source: mediawiki.Title.js@9df363d
sanitationRules = [
    # issue #101
    {"pattern": get_emoji_regexp(), "replace": ""},
    # "signature"
    {"pattern": re.compile(r"~{3}"), "replace": ""},
    # Space, underscore, tab, NBSP and other unusual spaces
    {
        "pattern": re.compile(
            r"[ _\u0009\u00A0\u1680\u180E\u2000-\u200A"
            r"\u2028\u2029\u202F\u205F\u3000\s]+"
        ),
        "replace": " ",
    },
    # issue #96
    {"pattern": re.compile(r"\u200B"), "replace": ""},
    # unicode bidi override characters: Implicit, Embeds, Overrides
    {"pattern": re.compile(r"[\u200E\u200F\u202A-\u202E]"), "replace": ""},
    # control characters
    {"pattern": re.compile(r"[\x00-\x1f\x7f]"), "replace": ""},
    # URL encoding (possibly)
    {"pattern": re.compile(r"%([0-9A-Fa-f]{2})"), "replace": r"% \1"},
    # HTML-character-entities
    {
        "pattern": re.compile(
            r"&(([A-Za-z0-9\x80-\xff]+|"
            r"#[0-9]+|#x[0-9A-Fa-f]+);)"
        ),
        "replace": r"& \1",
    },
    # slash, colon (not supported by file systems like NTFS/Windows,
    # Mac OS 9 [:], ext4 [/])
    {"pattern": re.compile(r"[:/#]"), "replace": "-"},
    # brackets, greater than
    {"pattern": re.compile(r"[\]\}>]"), "replace": ")"},
    # brackets, lower than
    {"pattern": re.compile(r"[\[\{<]"), "replace": "("},
    # directory structures
    {
        "pattern": re.compile(
            r"^(\.|\.\.|\./.*|\.\./.*|.*/\./.*|"
            r".*/\.\./.*|.*/\.|.*/\.\.)$"
        ),
        "replace": "",
    },
    # Pipes and backslashes
    {"pattern": re.compile(r"[|\\]"), "replace": "-"},
    # titleblacklist-custom-double-apostrophe
    {"pattern": re.compile(r"'{2,}"), "replace": '"'},
    # titleblacklist-custom-double-extension: the extension of the encoded file
    # is appended to the filename, so it must not already end with one.
    {
        "pattern": re.compile(
            r"(?:[.,](?:a?png|gif|jp[egs]g?|tiff?|xcf|pdf|midi?|kar|svg|djvu?|"
            r"og[avgx]|flac|opus|spx|wav|web[mp]|mp[ae23g]g?|stl)[ ,]*)+$",
            re.IGNORECASE,
        ),
        "replace": "",
        "error": "Your filename ends with a file extension: {!r}, please remove it",
    },
]


def get_filename_prefix_blacklist():
    """Get the filename prefix blacklist from Commons, cached in Redis."""
    cached = redisconnection.get(REDIS_PREFIX_BLACKLIST_KEY)
    if cached is not None:
        return json.loads(cached)

    prefixes = []

    for line in SITE.mediawiki_message("filename-prefix-blacklist").splitlines():
        line = line.strip()

        # Shave off comments from the line.
        if (comment_pos := line.find("#")) >= 0:
            line = line[:comment_pos].strip()

        if line:
            prefixes.append(line)

    # Save the prefix blacklist to the cache so we don't need to query Commons
    # every single time we validate a filename. These rules do not change often.
    redisconnection.set(
        REDIS_PREFIX_BLACKLIST_KEY, json.dumps(prefixes), ex=REDIS_PREFIX_BLACKLIST_TTL
    )

    return prefixes


def sanitize(filename):
    """Sanitize a filename for uploading."""
    for rule in sanitationRules:
        filename = rule["pattern"].sub(rule["replace"], filename)

    return filename.strip()


def capitalize_first_letter(input_string):
    """Capitalize the first letter of a string without affecting the rest."""
    if not input_string:
        return ""

    return input_string[0].upper() + input_string[1:]


def do_validate_filename(filename):
    """Validate filename for invalid characters/parts."""
    assert len(filename.encode("utf-8")) <= MAX_FILENAME_SIZE, (
        "Your filename is too long"
    )
    assert len(filename) == len(filename.lstrip()), (
        "Your filename contains leading spaces"
    )
    assert len(filename) == len(filename.rstrip()), (
        "Your filename contains trailing spaces"
    )

    for rule in sanitationRules:
        reobj = rule["pattern"].search(filename)
        assert not reobj or reobj.group(0) == " ", rule.get(
            "error", "Your filename contains a disallowed part: {!r}"
        ).format(reobj.group(0))

    # We check against the normalized version of the filename since the prefix
    # blacklist performs its validation after title capitalization.
    normalized = capitalize_first_letter(filename)

    for prefix in get_filename_prefix_blacklist():
        assert not normalized.startswith(prefix), (
            f"Your filename starts with a disallowed prefix: {prefix!r}, "
            "please choose a more descriptive name"
        )

    return filename.replace("_", " ")


def do_validate_filedesc(filedesc):
    """Validate filename for invalid characters/parts."""
    parse = SITE.simple_request(
        action="parse", text=filedesc, prop="externallinks"
    ).submit()

    externallinks = parse.get("parse", {}).get("externallinks", [])

    if externallinks:
        spam = SITE.simple_request(action="spamblacklist", url=externallinks).submit()

        assert spam.get("spamblacklist", {}).get("result") != "blacklisted", (
            "Your file description matches spam blacklist! Matches: {}".format(
                ", ".join(spam.get("spamblacklist", {}).get("matches", []))
            )
        )

    return filedesc


def do_validate_filename_unique(filename):
    """Validate filename isn't already in use on the wiki."""
    formats = set(WebVideoTranscode.settings.keys())

    # Capitalize the filename since all pages start with a capital letter, and
    # we need these values to match what MediaWiki returns for our comparison
    # to be accurate. Every letter except the first one is case-sensitive for
    # MediaWiki page titles.
    #
    # The built in 'capitalize()' method isn't used since it lowers the rest of
    # the string, which would also break the comparison.
    conflicting_names = {
        capitalize_first_letter(f"{filename}.{format}") for format in formats
    }

    pages = SITE.allpages(prefix=filename, namespace=NAMESPACE_FILE)
    for page in pages:
        assert page.title(with_ns=False) not in conflicting_names, (
            f"A filename with the same name already exists: {page.full_url()}"
        )

    return filename


def do_validate_youtube_id(youtube_id):
    """Query Commons to find an entity with a specific YouTube ID."""

    query = f"""
        SELECT ?file WHERE {{
            ?file wdt:P1651 "{youtube_id}".
        }}
        LIMIT 1
    """
    results = WcqsSession().query(query)

    if len(results["results"]["bindings"]) == 0:
        return None

    return results["results"]["bindings"][0]["file"]["value"]
