<?php
$protocol = (isset($_SERVER['SERVER_PROTOCOL']) ? $_SERVER['SERVER_PROTOCOL'] : 'HTTP/1.0');
header($protocol . ' 301 Moved Permanently');
header("Location: index.py");
