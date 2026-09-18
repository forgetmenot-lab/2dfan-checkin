#!/bin/sh
set -eu
exec docker run --rm --shm-size=256m \
  --env-file /volume1/docker/2dfan-nas/.env \
  2dfan-checkin
