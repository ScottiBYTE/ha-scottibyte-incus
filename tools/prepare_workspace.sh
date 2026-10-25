#!/usr/bin/env bash
# Run from the unpacked repository as scott inside ScottiBYTE-Incus.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run this as your normal scott user, not root.' >&2
    exit 1
fi
repo_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_directory"
sudo apt-get update
sudo apt-get install -y git unzip ca-certificates openssh-client python3-venv python3-pip
if [ ! -d .git ]; then
    git init -b main
fi
git config --local user.name 'ScottiBYTE'
git config --local user.email 'vmsman@scottibyte.com'
echo 'Source workspace prepared. Git author: ScottiBYTE <vmsman@scottibyte.com>'
echo 'No GitHub repository has been created or pushed.'
