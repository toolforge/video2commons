#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# Wrapper around http://www.ivarch.com/programs/pv.shtml
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

import subprocess
import threading
import time

class TransferStatus(threading.Thread):
    def __init__(self, inf, outf, totalsize=None, pvpath='/usr/bin/pv'):
        super(TransferStatus, self).__init__()
        self.inf = inf
        self.outf = outf
        self.totalsize = totalsize
        self.pvpath = pvpath
        self.status = 0
        self.ret = 0
	
    def run(self):
        pv = subprocess.Popen([self.pvpath, '-n'] + (['-s', str(self.totalsize)] if self.totalsize else []),
            stdin=self.inf, stdout=self.outf, stderr=subprocess.PIPE)
        while pv.poll() is None:
#            for line in pv.stderr.readlines(): # http://bugs.python.org/issue3907
            while True:
                line = pv.stderr.readline()
                if not line: break

                self.status = int(line)

            time.sleep(0.5)

        self.outf.close()
        self.ret = pv.returncode

def main():
    import os, sys
    inf = open('test', 'r')
    dump = open('/dev/null', 'w')
    process = subprocess.Popen(['/bin/gzip', '-9'], stdin=subprocess.PIPE, stdout=dump, stderr=sys.stderr)
    status = TransferStatus(inf, process.stdin, os.path.getsize('test'))
    status.start()
    while process.poll() is None:
        print status.status
        time.sleep(0.5)

if __name__ == '__main__':
    main()