#!/bin/sh

find /srv/v2coutput/* -type d -ctime +15 -exec rm -r {} \;