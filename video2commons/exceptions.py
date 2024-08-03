#!/usr/bin/env python3
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#

"""video2commons exceptions."""


class TaskError(Exception):
    """A generic task error exception."""

    def __init__(self, desc):
        """Initialize."""
        super().__init__(desc)
        self.desc = desc

    def __reduce__(self):
        """Helper for pickling."""
        return (self.__class__, (self.desc,))


class NeedServerSideUpload(TaskError):
    """A server server-side is needed."""

    # So no one should handle it
    def __init__(self, url, hashsum=None):
        """Initialize."""
        super().__init__(url)
        self.url = url
        self.hashsum = hashsum


class TaskAbort(TaskError):
    """The task has been aborted."""

    def __init__(self):
        """Initialize."""
        super().__init__('The task has been aborted.')

