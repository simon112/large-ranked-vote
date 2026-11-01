#!/bin/sh
# Copy the app into /opt/poll (root-owned, read-only to the service), install the units, restart.
set -eu
cd "$(dirname "$0")"
sudo install -d -o root -g root -m 0755 /opt/poll /opt/poll/static
# The service's empty root directory (see RootDirectory= in poll.service).
sudo install -d -o root -g root -m 0755 /opt/poll-root
sudo install -o root -g root -m 0644 server.py /opt/poll/server.py
sudo install -o root -g root -m 0644 static/*.html /opt/poll/static/
sudo install -o root -g root -m 0644 poll.service poll.socket /etc/systemd/system/
sudo systemctl daemon-reload
# The socket must own the port before the service starts; stopping first frees it if the
# service was bound to it directly (before socket activation). Connections arriving during the
# restart wait in the socket's queue rather than being refused.
sudo systemctl stop poll.service
sudo systemctl enable --now poll.socket
sudo systemctl start poll.service
systemctl is-active poll.socket poll.service
