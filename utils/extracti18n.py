#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2011-2015 Krinkle
# Originally from intuition scripts/getLangData.php under CC-BY 3.0
# Copyright (C) 2016 Zhuyifei1999
# Translation to Python and re-licensed to GPL
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#

"""Extract language data from MediaWiki core."""

import os
import sys
import re
import json

if not len(sys.argv) > 1 or "/messages" not in sys.argv[1]:
    print(
        (
            "usage: python " + sys.argv[0] + " <dir>\n\n"
            "  <dir>  The path to mediawiki/languages/messages\n"
        )
    )
    sys.exit(1)

msgDir = sys.argv[1]

dest = (
    os.path.dirname(os.path.realpath(__file__))
    + "/../video2commons/frontend/i18n-metadata"
)

data = {
    "fallbacks": {},
    "rtl": [],
    "alllangs": [],
}
rFallback = re.compile(r"fallback = '(.*?)'", re.I)
rIsRtl = re.compile(r"rtl = true", re.I)
for file in os.listdir(msgDir):
    filePath = msgDir + "/" + file
    if file in [".", ".."] or not os.path.isfile(filePath):
        continue

    with open(filePath, "r") as openfile:
        content = openfile.read()

    fileMatch = re.match(r"Messages(.*?)\.php", file)
    source = fileMatch.group(1).lower().replace("_", "-")
    contentMatch = rFallback.search(content)
    if contentMatch:
        fallbacks = [s.strip() for s in contentMatch.group(1).split(",")]
        data["fallbacks"][source] = fallbacks if len(fallbacks) > 1 else fallbacks[0]

    if rIsRtl.search(content):
        data["rtl"].append(source)

    data["alllangs"].append(source)


def _write(key):
    dest_file = dest + "/" + key + ".json"
    with open(dest_file, "w") as openfile:
        json.dump(data[key], openfile, sort_keys=True, indent=4, separators=(",", ": "))


for key in data:
    _write(key)
