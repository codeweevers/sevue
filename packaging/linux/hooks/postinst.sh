#!/usr/bin/env bash
set -u

echo "[sevue] post-install: configuring virtual camera dependencies"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update || true
  apt-get install -y v4l2loopback-dkms v4l2loopback-utils v4l-utils || true
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y kmod-v4l2loopback v4l2loopback-utils v4l-utils || \
  dnf install -y v4l2loopback-dkms v4l2loopback-utils v4l-utils || true
elif command -v yum >/dev/null 2>&1; then
  yum install -y kmod-v4l2loopback v4l2loopback-utils v4l-utils || \
  yum install -y v4l2loopback-dkms v4l2loopback-utils v4l-utils || true
fi

if command -v modprobe >/dev/null 2>&1; then
  modprobe v4l2loopback devices=1 video_nr=10 card_label="Sevue-VirtualCam" exclusive_caps=1 || true
fi

exit 0
