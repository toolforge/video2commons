# Puppet Configuration

This directory contains the Puppet manifest for the video2commons worker backend.

## Required Modules

The following Puppet modules are required:

* [puppet/cron](https://forge.puppet.com/modules/puppet/cron)
* [puppet/nodejs](https://forge.puppet.com/modules/puppet/nodejs)
* [puppetlabs/apt](https://forge.puppet.com/modules/puppetlabs/apt)

## Service supervision

The `v2ccelery` systemd unit is configured to survive OOM kills of an encode
(`OOMPolicy=continue`, `MemoryMax=90%`), to be restarted when its main process
exits (`Restart=always`) and to never leave orphan `ffmpeg` processes behind
(`ExecStopPost`). The unit has an infinite `TimeoutStopSec` to let running tasks
finish on a restart, so an orphan would otherwise block it in `deactivating`
forever.

`utils/healthcheck.sh` runs every 5 minutes as root and restarts the service if
it is down or has not answered to `celery inspect ping` for 288 consecutive runs (about 24 hours), and force kills a unit
stuck while stopping. `utils/deploy-cloudvps-encoders.sh` runs it with `--check`
after `puppet apply`, since Puppet only queues the restart (`--no-block`), and
fails the deployment if the worker does not become healthy.
