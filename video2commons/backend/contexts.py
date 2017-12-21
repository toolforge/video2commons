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
# along with self program.  If not, see <http://www.gnu.org/licenses/>
#

"""video2commons backend contexts."""

from __future__ import absolute_import, unicode_literals

import contextlib
import os
import shutil
import threading

import pywikibot


@contextlib.contextmanager
def outputdir():
    """chdir to a temporary directory in /srv/v2c/output/."""
    for i in range(10):  # 10 tries
        id = os.urandom(8).encode('hex')
        outputdir = '/srv/v2c/output/' + id
        if not os.path.isdir(outputdir):
            os.mkdir(outputdir)
            break
    else:
        # the chance is hitting this is so low that it's not gonna worth the
        # time writing an error message
        assert False

    old_cwd = os.getcwd()
    os.chdir(outputdir)

    try:
        yield
    finally:
        assert os.getcwd() == outputdir
        os.chdir(old_cwd)
        shutil.rmtree(outputdir)


pwb_login_lock = threading.Lock()


@contextlib.contextmanager
def pwb_login(username, oauth):
    """Login to Commons with pywikibot via oAuth."""
    # The same process cannot run two logins at a time. This is not a race
    # condition issue; this is a security issue.
    with pwb_login_lock:
        assert not pywikibot.config.usernames['commons']
        assert not pywikibot.config.authenticate

        pywikibot.config.usernames['commons']['commons'] = username
        pywikibot.config.authenticate['commons.wikimedia.org'] = oauth
        pywikibot.Site('commons', 'commons', user=username).login()

        try:
            yield
        finally:
            assert pywikibot.config.usernames['commons']
            assert pywikibot.config.authenticate

            pywikibot.stopme()
            pywikibot.config.authenticate.clear()
            pywikibot.config.usernames['commons'].clear()
            pywikibot._sites.clear()
