#!/bin/sh
# Copy the app into /opt/poll (root-owned, read-only to the service) and restart it.
set -eu
cd "$(dirname "$0")"
sudo install -d -o root -g root -m 0755 /opt/poll /opt/poll/static
# The service's empty root directory (see RootDirectory= in poll.service).
sudo install -d -o root -g root -m 0755 /opt/poll-root
sudo install -o root -g root -m 0644 server.py /opt/poll/server.py
sudo install -o root -g root -m 0644 static/*.html /opt/poll/static/
sudo install -o root -g root -m 0644 poll.service /etc/systemd/system/poll.service
sudo systemctl daemon-reload
sudo systemctl restart poll
systemctl is-active poll
