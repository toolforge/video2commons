#!/bin/bash

# Note: All ssh commands share the same connection for the lifetime of this
# script if run via the workflow at .github/workflows/toolforge-deployment.yml.
#
# The follow ssh options are used by the workflow:
#     ControlMaster auto
#     ControlPath ~/.ssh/sockets/%r@%h-%p
#     ControlPersist 60

bastion_host=login.toolforge.org

repo_path="/data/project/video2commons"

if [ -z "$V2C_USERNAME" ]; then
    echo "Error: V2C_USERNAME environment variable is not set" >&2
    exit 1
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$script_dir/.."

echo "Updating video2commons frontend..."

# Pull in the latest changes from the repository currently in master.
ssh "$V2C_USERNAME@$bastion_host" "become video2commons bash -c 'cd $repo_path && git pull'"

if [ $? -ne 0 ]; then
    echo "Failed to pull most recent changes for v2c" >&2
    exit 1
fi

# Create a temp directory for temporarily storing the minified files.
ssh "$V2C_USERNAME@$bastion_host" "mkdir -p /tmp/v2c-deploy"

if [ $? -ne 0 ]; then
    echo "Failed to create temporary directory at /tmp/v2c-deploy" >&2
    exit 1
fi

# Upload the minified files to the new temp directory.
scp "$repo_root/video2commons/frontend/static/"*.min.js \
    "$repo_root/video2commons/frontend/templates/"*.min.html \
    "$V2C_USERNAME@$bastion_host:/tmp/v2c-deploy/"

if [ $? -ne 0 ]; then
    echo "Failed to copy minified files to remote" >&2
    ssh "$V2C_USERNAME@$bastion_host" "rm -rf /tmp/v2c-deploy"
    exit 1
fi

# Copy the minified files to destination with correct ownership, then cleanup.
ssh "$V2C_USERNAME@$bastion_host" "become video2commons bash -c '
    cp /tmp/v2c-deploy/*.min.js $repo_path/video2commons/frontend/static/
    cp /tmp/v2c-deploy/*.min.html $repo_path/video2commons/frontend/templates/
' && rm -rf /tmp/v2c-deploy"

if [ $? -ne 0 ]; then
    echo "Failed to move minified files to destination" >&2
    exit 1
fi

# Restart the webservice so any Python changes are applied.
ssh "$V2C_USERNAME@$bastion_host" "become video2commons toolforge webservice python3.11 restart"

# Cleanup the SSH control socket that we use to keep the connection alive
# across multiple ssh command executions.
ssh -O exit "$V2C_USERNAME@$bastion_host" 2>/dev/null || true

echo "Done"
