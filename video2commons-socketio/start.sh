#!/bin/bash
#
# Starts the Socket.IO server. The Toolforge webservice runs it through
# `npm start` in $HOME/www/js (see the "start" script in package.json).
#
# Toolforge's newest Node.js image is too old, so the server runs with a
# Node.js version installed with nvm in the tool's home instead, as described
# in https://wikitech.wikimedia.org/wiki/Help:Toolforge/Node.js#Using_other_versions_of_node
#
# nvm must be installed once, as the tool (see docs/ci-cd.md). To change the
# Node.js version, update NODE_VERSION: it is installed on the next start.

set -eo pipefail

NODE_VERSION=26.12.1
NODE_BIN="$HOME/.nvm/versions/node/v$NODE_VERSION/bin"

if [ ! -x "$NODE_BIN/node" ]; then
    if [ ! -s "$HOME/.nvm/nvm.sh" ]; then
        echo "Node.js $NODE_VERSION is missing and nvm is not installed in ~/.nvm" >&2
        exit 1
    fi
    # shellcheck source=/dev/null
    . "$HOME/.nvm/nvm.sh"
    nvm install "$NODE_VERSION"
fi

export PATH="$NODE_BIN:$PATH"
echo "Starting with Node.js $(node --version)"

# Install the production dependencies exactly as locked in package-lock.json.
cd "$HOME"
npm ci --omit=dev --no-audit --no-fund

exec node "$HOME/www/js/server.js"
