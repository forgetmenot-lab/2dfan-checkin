#!/bin/sh
LOG=/volume1/docker/2dfan-nas/scheduler.log
exec >> "$LOG" 2>&1
echo "===== 실행 시작 ====="
date
DOCKER=$(command -v docker)
if [ -z "$DOCKER" ]; then
  for p in /usr/local/bin/docker /usr/bin/docker /var/packages/ContainerManager/target/usr/bin/docker /var/packages/Docker/target/usr/bin/docker; do
    if [ -x "$p" ]; then DOCKER="$p"; break; fi
  done
fi
if [ -z "$DOCKER" ]; then
  echo "오류: docker 실행 파일을 찾지 못했습니다."
  exit 1
fi
"$DOCKER" run --rm --shm-size=256m --network "${CHECKIN_DOCKER_NETWORK:-bridge}" \
  -v /volume1/docker/2dfan-nas/api.py:/app/api.py:ro \
  -v /volume1/docker/2dfan-nas/main.py:/app/main.py:ro \
  -v /volume1/docker/2dfan-nas/results.py:/app/results.py:ro \
  --env-file /volume1/docker/2dfan-nas/.env \
  2dfan-checkin
RESULT=$?
echo "===== 실행 종료: 코드 $RESULT ====="
date
exit "$RESULT"
