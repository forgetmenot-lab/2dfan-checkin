#!/bin/sh
# Run as a DSM scheduled task only after the account has been unlocked.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -f "$ROOT/.env" ]; then
  echo "출석 설정 파일이 없습니다: $ROOT/.env (파일 이름 앞의 점을 확인하세요.)"
  exit 1
fi
DOCKER=$(command -v docker || true)
if [ -z "$DOCKER" ]; then
  for p in /usr/local/bin/docker /usr/bin/docker /var/packages/ContainerManager/target/usr/bin/docker; do
    if [ -x "$p" ]; then DOCKER="$p"; break; fi
  done
fi
if [ -z "$DOCKER" ]; then echo "docker를 찾지 못했습니다."; exit 1; fi
# Bounded wait; never fall back to the NAS default network.
attempt=0
while [ "$attempt" -lt 12 ]; do
  health=$("$DOCKER" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2dfan-vpn 2>/dev/null || true)
  [ "$health" = healthy ] && break
  attempt=$((attempt + 1))
  sleep 5
done
if [ "$health" != healthy ]; then
  echo "VPN이 정상 연결되지 않아 출석 실행을 중단했습니다."
  exit 1
fi
"$DOCKER" run --rm --shm-size=256m --network container:2dfan-vpn \
  --env-file "$ROOT/.env" -e CHECKIN_PROXY= 2dfan-checkin
