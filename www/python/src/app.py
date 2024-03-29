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

"""video2commons web frontend wrapper."""



import os
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../../../")

from video2commons.frontend import app  # NOQA

if __name__ == '__main__':
    app.run()
