$consumer_key = 'REDACTED'
$consumer_secret = 'REDACTED'
$redis_pw = 'REDACTED'
$redis_host = 'video-redis.video.eqiad.wmflabs'
$http_host = 'v2c.wmflabs.org'

## BASIC INSTANCE SETUP

# include role::labs::lvm::srv

package { [
    'build-essential',
    'python-dev',
    'python-setuptools',
]:
    ensure => present,
}

package { [
    'git',
    'wget'
]:
    ensure => present,
}

package { [
    'ffmpeg',
    'ffmpeg2theora',
    'gstreamer0.10-plugins-good',
    'gstreamer0.10-plugins-ugly',
    'gstreamer0.10-plugins-bad',
]:
    ensure => latest,
}

exec { 'install-pip':
    command => '/usr/bin/easy_install pip',
    creates => '/usr/local/bin/pip',
    require => Package['python-setuptools'],
}

package { 'youtube-dl':
    ensure   => latest,
    provider => 'pip',
    require  => Exec['install-pip'],
}

package { 'nginx':
    ensure => present,
}

service { 'nginx':
    ensure  => running,
    enable  => true,
    require => Package['nginx']
}

## V2C BACKEND SETUP

exec { 'check-srv-mounted':
    command => '/bin/mount | /bin/grep /srv',
}

exec { 'git-clone-v2c':
    command => '/usr/bin/git clone https://github.com/Toollabs/video2commons.git /srv/v2c',
    creates => '/srv/v2c/.git/config',
    require => [
        Package['git'],
        Exec['check-srv-mounted'],
    ],
}

file { [
    '/srv/v2c/output',
    '/srv/v2c/apicache',
]:
    ensure  => directory,
    owner   => 'tools.video2commons',
    group   => 'tools.video2commons',
    require => Exec['git-clone-v2c'],
    before  => Service['v2ccelery'],
}

file { '/srv/v2c/ssu':
    ensure  => link,
    target  => '/data/scratch/video2commons/ssu/',
    require => Exec['git-clone-v2c'],
    before  => Service['v2ccelery'],
}

file { '/srv/v2c/throttle.ctrl':
    ensure  => present, # content managed by pywikibot
    owner   => 'tools.video2commons',
    group   => 'tools.video2commons',
    require => Exec['git-clone-v2c'],
    before  => Service['v2ccelery'],
}

$config_json_template = '{
"consumer_key": "<%= @consumer_key %>",
"consumer_secret": "<%= @consumer_secret %>",
"api_url": "https://commons.wikimedia.org/w/index.php",
"redis_pw": "<%= @redis_pw %>",
"redis_host": "<%= @redis_host %>",
"http_host": "<%= @http_host %>"
}
'

file { '/srv/v2c/config.json':
    ensure  => file,
    content => inline_template($config_json_template),
    require => Exec['git-clone-v2c'],
    notify  => Service['v2ccelery'],
}

package { 'libmysqlclient-dev': # wanted by some pip packages
    ensure => present,
}

exec { 'pip-install-requirements':
    command => '/usr/local/bin/pip install -Ur /srv/v2c/requirements.txt',
    require => [
        Exec['install-pip'],
        Exec['git-clone-v2c'],
        Package['python-dev'],
        Package['build-essential'],
        Package['libmysqlclient-dev'],
    ],
    before  => Service['v2ccelery'],
}

# lint:ignore:single_quote_string_with_variables
$celeryd_service = '# THIS FILE IS MANAGED BY MANUAL PUPPET
[Unit]
Description=v2c celery Service
After=network.target

[Service]
Type=forking
User=tools.video2commons
Group=tools.video2commons
EnvironmentFile=-/etc/default/v2ccelery
WorkingDirectory=/srv/v2c
Restart=on-failure
ExecStart=/bin/sh -c \'${CELERY_BIN} multi start $CELERYD_NODES \
    -A $CELERY_APP --logfile=${CELERYD_LOG_FILE} \
    --pidfile=${CELERYD_PID_FILE} $CELERYD_OPTS\'
ExecStop=/bin/sh -c \'${CELERY_BIN} multi stopwait $CELERYD_NODES \
    --pidfile=${CELERYD_PID_FILE}\'
ExecReload=/bin/sh -c \'${CELERY_BIN} multi restart $CELERYD_NODES \
    -A $CELERY_APP --pidfile=${CELERYD_PID_FILE} --logfile=${CELERYD_LOG_FILE} \
    --loglevel="${CELERYD_LOG_LEVEL}" $CELERYD_OPTS\'

[Install]
WantedBy=multi-user.target
'
# lint:endignore

file { '/lib/systemd/system/v2ccelery.service':
    ensure  => file,
    content => $celeryd_service,
    require => File['/etc/default/v2ccelery'],
    notify  => Service['v2ccelery'],
}

$celeryd_config = '# THIS FILE IS MANAGED BY MANUAL PUPPET
CELERYD_NODES=2
CELERY_BIN="/usr/local/bin/celery"
CELERY_APP="video2commons.backend.worker"
CELERYD_MULTI="multi"
CELERYD_LOG_FILE="/var/log/v2ccelery/%N.log"
CELERYD_PID_FILE="/var/run/v2ccelery/%N.pid"
CELERYD_USER="tools.video2commons"
CELERYD_GROUP="tools.video2commons"
CELERY_CREATE_DIRS=1
'

file { '/etc/default/v2ccelery':
    ensure  => file,
    content => $celeryd_config,
    require => [
        File['/var/run/v2ccelery'],
        File['/var/log/v2ccelery'],
    ],
    notify  => Service['v2ccelery'],

}

$tmpfiles_config = '# THIS FILE IS MANAGED BY MANUAL PUPPET
d /var/run/v2ccelery 1777 root root -
d /var/log/v2ccelery 1777 root root -'

file { '/usr/lib/tmpfiles.d/v2ccelery.conf':
    ensure  => file,
    content => $tmpfiles_config,
}

file { [
    '/var/run/v2ccelery',
    '/var/log/v2ccelery',
]:
    ensure  => directory,
    owner   => 'tools.video2commons',
    group   => 'tools.video2commons',
    before  => Service['v2ccelery'],
    require => File['/usr/lib/tmpfiles.d/v2ccelery.conf'],
}

service { 'v2ccelery':
    ensure  => running,
    enable  => true,
    require => Package['ffmpeg'],
}

$logrotate_config = '# THIS FILE IS MANAGED BY MANUAL PUPPET
/var/log/v2ccelery/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    copytruncate
}
'

file { '/etc/logrotate.d/v2ccelery':
    ensure  => file,
    content => $logrotate_config,
    require => Service['v2ccelery'],
}

$nginx_config_template = '# THIS FILE IS MANAGED BY MANUAL PUPPET
server {
    listen 80;
    listen [::]:80;

    root /srv/v2c/ssu;

    server_name <%= @http_host %>;

    location / {
        try_files $uri $uri/ =404;
    }

    location = / {
        return 302 https://tools.wmflabs.org/video2commons/;
    }
}
'

file { '/etc/nginx/sites-available/video2commons':
    ensure  => file,
    content => inline_template($nginx_config_template),
    require => Service['v2ccelery'],
}

file { '/etc/nginx/sites-enabled/video2commons':
    ensure  => link,
    target  => '/etc/nginx/sites-available/video2commons',
    require => File['/etc/nginx/sites-available/video2commons'],
    notify  => Service['nginx'],
}

cron { 'v2ccleanup':
    command => '/bin/sh /srv/v2c/video2commons/backend/cleanup.sh',
    user    => 'tools.video2commons',
    minute  => '48',
    require => Service['v2ccelery'],
}
