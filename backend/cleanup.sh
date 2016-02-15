#!/bin/sh

find /srv/v2coutput/* -type d -ctime +7 -exec rm -r {} \;