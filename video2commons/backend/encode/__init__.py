#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General License for more details.
#
# You should have received a copy of the GNU General License
# along with self program.  If not, see <https://www.gnu.org/licenses/>
#

"""Main encode module."""

import os

from .globals import ffmpeg_location, ffprobe_location
from .helpers import get_video
from .transcode import WebVideoTranscode
from .transcodejob import WebVideoTranscodeJob

# https://github.com/senko/python-video-converter
from converter import Converter


def encode(source, origkey, statuscallback=None, errorcallback=None, concurrency=None):
    """Main encode function."""
    source = os.path.abspath(source)
    preserve = {"video": False, "audio": False}

    c = Converter(ffmpeg_path=ffmpeg_location, ffprobe_path=ffprobe_location)
    info = c.probe(source)

    targettype = WebVideoTranscode.settings.get(origkey)
    key = getbestkey(info, targettype, origkey) or origkey
    targettype = WebVideoTranscode.settings.get(key)

    if info and targettype:
        video = get_video(info)

        if video and video.codec == targettype.get("videoCodec"):
            preserve["video"] = True
        if info.audio and info.audio.codec == targettype.get("audioCodec"):
            preserve["audio"] = True

    target = source + "." + key
    job = WebVideoTranscodeJob(
        source,
        target,
        key,
        preserve,
        statuscallback,
        errorcallback,
        info,
        concurrency,
    )

    return target if job.run() else None


def getbestkey(info, targettype, origkey):
    """Find the best convert key to use."""

    assert info, "The file format could not be recognized"
    assert targettype, "The target format is invalid."

    video = get_video(info)
    no_video = "novideo" in targettype or not video
    no_audio = "noaudio" in targettype or not info.audio

    if no_video and no_audio:
        raise ValueError(
            "The resulting file won't have any video or audio tracks. "
            "Check your import settings and try again."
        )

    # Check if we need to handle video only, and if no codec change is required.
    if targettype.get("videoCodec") and no_audio:
        for newkey, newtargettype in list(WebVideoTranscode.settings.items()):
            if (
                video.codec == newtargettype.get("videoCodec")
                and "noaudio" in newtargettype
            ):
                return newkey

    # Check if we need to handle audio only, and if no codec change is required.
    if targettype.get("audioCodec") and no_video:
        for newkey, newtargettype in list(WebVideoTranscode.settings.items()):
            if (
                info.audio.codec == newtargettype.get("audioCodec")
                and "novideo" in newtargettype
            ):
                return newkey

    # Check if we need to handle both video and audio, and if no codec change
    # is required for both of them.
    if (
        targettype.get("videoCodec")
        and targettype.get("audioCodec")
        and video
        and info.audio
    ):
        for newkey, newtargettype in list(WebVideoTranscode.settings.items()):
            if video.codec == newtargettype.get(
                "videoCodec"
            ) and info.audio.codec == newtargettype.get("audioCodec"):
                return newkey

    # No matches found, which means we're dealing with non-free formats.

    # Check if the source has no audio track and fall back to no-audio variant
    # if desired target erroneously has audio specified when it shouldn't.
    if not info.audio and "noaudio" not in targettype:
        an_key = f"an.{origkey}"
        if an_key in WebVideoTranscode.settings:
            return an_key

    # Check if the source has no video track and fall back to no-video variant
    # if the desired target erroneously has video specified when it shouldn't.
    if not video and "novideo" not in targettype:
        if targettype.get("audioCodec") == "vorbis":
            return "ogg"
        elif targettype.get("audioCodec") == "opus":
            return "opus"

    return None
