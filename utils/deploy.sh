#!/bin/bash

encoder_hosts=$(cat <<EOF
encoding01.video.eqiad1.wikimedia.cloud
encoding02.video.eqiad1.wikimedia.cloud
encoding03.video.eqiad1.wikimedia.cloud
encoding04.video.eqiad1.wikimedia.cloud
encoding05.video.eqiad1.wikimedia.cloud
encoding06.video.eqiad1.wikimedia.cloud
EOF
)

bastion_host=login.toolforge.org

script_dir="$(cd "$(dirname "$0")" && pwd)"
backend_pp="$script_dir/../puppet/backend.pp"

if [ ! -f "$backend_pp" ]; then
    echo "Error: Puppet manifest not found at '$backend_pp'" >&2
    exit 1
elif [ -z "$V2C_USERNAME" ]; then
    echo "Error: V2C_USERNAME environment variable is not set" >&2
    exit 1
elif [ -z "$V2C_CONSUMER_KEY" ]; then
    echo "Error: V2C_CONSUMER_KEY environment variable is not set" >&2
    exit 1
elif [ -z "$V2C_CONSUMER_SECRET" ]; then
    echo "Error: V2C_CONSUMER_SECRET environment variable is not set" >&2
    exit 1
elif [ -z "$V2C_REDIS_PW" ]; then
    echo "Error: V2C_REDIS_PW environment variable is not set" >&2
    exit 1
fi

# Patch the puppet manifest to include secrets that aren't in the repository.
# The values being substituted in are alphanumeric and are safe to use. Convert
# the manifest to base64 as well to prevent escaping issues when stuffing it
# into the script.
patched_manifest=$(sed -E "
    s/^\\\$consumer_key[[:space:]]*=[[:space:]]*'REDACTED'/\\\$consumer_key = '$V2C_CONSUMER_KEY'/
    s/^\\\$consumer_secret[[:space:]]*=[[:space:]]*'REDACTED'/\\\$consumer_secret = '$V2C_CONSUMER_SECRET'/
    s/^\\\$redis_pw[[:space:]]*=[[:space:]]*'REDACTED'/\\\$redis_pw = '$V2C_REDIS_PW'/
    " "$backend_pp" | base64)

# Create the script to be run on the remote hosts that drops the manifest into
# /tmp, runs the apply script, and reloads the service.
apply_script=$(cat <<EOF
echo -n "$patched_manifest" | base64 -d > /tmp/backend.pp

sudo puppet apply /tmp/backend.pp --debug

if [ \$? -ne 0 ]; then
    rm /tmp/backend.pp
    exit 1
else
    rm /tmp/backend.pp
fi
EOF
)

while read -r encoder_host; do
    echo "Applying puppet manifest to '$encoder_host' and restarting v2c service..."

    ssh -J "$V2C_USERNAME@$bastion_host" "$V2C_USERNAME@$encoder_host" 'bash -s' <<< "$apply_script"

    if [ $? -ne 0 ]; then
        echo "Failed to apply puppet manifest to '$encoder_host'" >&2
    else
        echo "Puppet manifest applied to '$encoder_host'"
    fi
done <<< "$encoder_hosts"

echo "Done"
