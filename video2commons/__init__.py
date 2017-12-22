#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2016 Zhuyifei1999
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

"""videocommons package."""

from __future__ import absolute_import

from video2commons import config
from video2commons import exceptions
from video2commons import backend
from video2commons import frontend

__all__ = ['config', 'exceptions', 'backend', 'frontend']
