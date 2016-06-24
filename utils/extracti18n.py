#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2011-2015 Krinkle
# Originally from intuition scripts/getLangData.php under CC-BY 3.0
# Copyright (C) 2016 Zhuyifei1999
# Tranlation to Python and re-licensed to GPL
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

"""Extract language data from MediaWiki core."""

import os
import sys
import re
import json

if not len(sys.argv) > 1 or '/messages' not in sys.argv[1]:
    print ("usage: python " + sys.argv[0] + " <dir>\n\n"
           "  <dir>  The path to mediawiki/languages/messages\n")
    sys.exit(1)

msgDir = sys.argv[1]
if not os.path.isdir(msgDir) or not os.access(msgDir, os.R_OK):
    print "error: Path to languages/messages not found\n"
    sys.exit(1)

dest = os.path.dirname(os.path.realpath(__file__)) + \
    '/../video2commons/frontend/i18n'
if not os.path.isdir(dest) or not os.access(dest, os.W_OK):
    print "error: Unable to write to $dest\n"
    sys.exit(1)

data = {
    'fallbacks': {},
    'rtl': [],
}
rFallback = re.compile(r"fallback = '(.*?)'", re.I)
rIsRtl = re.compile(r'rtl = true', re.I)
for file in os.listdir(msgDir):
    filePath = msgDir + "/" + file
    if file in ['.', '..'] or not os.path.isfile(filePath):
        continue

    with open(filePath, 'r') as openfile:
        content = openfile.read()

    fileMatch = re.match(r'Messages(.*?)\.php', file)
    source = fileMatch.group(1).lower().replace('_', '-')
    contentMatch = rFallback.search(content)
    if contentMatch:
        fallbacks = [s.strip() for s in contentMatch.group(1).split(',')]
        data['fallbacks'][source] = \
            fallbacks if len(fallbacks) > 1 else fallbacks[0]

    if rIsRtl.search(content):
        data['rtl'].append(source)

destFile = dest + "/fallbacks.json"
with open(destFile, 'w') as openfile:
    json.dump(data['fallbacks'], openfile, sort_keys=True,
              indent=4, separators=(',', ': '))

destFile = dest + "/rtl.json"
with open(destFile, 'w') as openfile:
    json.dump(data['rtl'], openfile, sort_keys=True,
              indent=4, separators=(',', ': '))
