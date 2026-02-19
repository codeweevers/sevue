#!/usr/bin/env bash
set -u

echo "[sevue] post-remove: unloading virtual camera module when possible"

if command -v modprobe >/dev/null 2>&1; then
  modprobe -r v4l2loopback || true
fi

exit 0
