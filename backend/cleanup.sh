#!/bin/sh

find /srv/v2c/output/* -type d -ctime +1 -exec rm -rv {} \;
find /srv/v2c/ssu/* -type d -ctime +1 -exec rm -rv {} \;