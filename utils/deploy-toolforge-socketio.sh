#!/bin/bash

# Note: All ssh commands share the same connection for the lifetime of this
# script if run via the workflows.
#
# The follow ssh options are used by the workflow:
#     ControlMaster auto
#     ControlPath ~/.ssh/sockets/%r@%h-%p
#     ControlPersist 60

bastion_host=login.toolforge.org

if [ -z "$V2C_USERNAME" ]; then
    echo "Error: V2C_USERNAME environment variable is not set" >&2
    exit 1
elif [ -z "$V2C_SERVICE_NAME" ]; then
    echo "Error: V2C_SERVICE_NAME environment variable is not set" >&2
    exit 1
fi

remote_repo_path="/data/project/$V2C_SERVICE_NAME"

echo "Updating video2commons socket.io backend..."

# Pull in the latest changes from the repository currently in master.
ssh "$V2C_USERNAME@$bastion_host" "become $V2C_SERVICE_NAME bash -c 'cd $remote_repo_path && git pull'"

if [ $? -ne 0 ]; then
    echo "Failed to pull most recent changes for v2c" >&2
    exit 1
fi

# Restart the webservice so any JavaScript changes are applied.
ssh "$V2C_USERNAME@$bastion_host" "become $V2C_SERVICE_NAME toolforge webservice --backend=kubernetes node18 restart"

# Cleanup the SSH control socket that we use to keep the connection alive
# across multiple ssh command executions.
ssh -O exit "$V2C_USERNAME@$bastion_host" 2>/dev/null || true

echo "Done"
