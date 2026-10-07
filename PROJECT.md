# 프로젝트 구조

- `api.py`: 계정별 Chrome 실행 → 세션 주입 → `/checkin` 방문 → `currentUserId` 검증 → 상태 조회 → 일일 출석 버튼/인증 팝업 처리 → 서버 상태 재조회.
- `results.py`: 출석 결과와 현재 보유 포인트 모델, 한국어 결과 문구.
- `main.py`: 계정 로딩/순차 실행/360초 제한, 성공·기완료·실패 요약, Discord 호출.
- `notify.py`: 표준 라이브러리 기반 Discord 웹훅, 멘션 차단, 길이 제한과 429 처리.
- `Dockerfile`: Python 3.12, Chrome (amd64), Xvfb, nodriver 0.48.1.
- `entrypoint.sh`: Xvfb 시작, 기존 nodriver 연결 재시도 패치, main 실행. 애플리케이션 소스를 실행 시 덮어쓰지 않습니다.
- `docker-compose.yml`, `run-nas.sh`: 한 번 실행하는 배포 예시. 주기 설정은 NAS 담당.
- `tests/`: 외부 출석/알림 전송 없이 실행하는 회귀 테스트.
- `run-scheduler.sh`: Docker 경로 검색, 세 파일 마운트, 실행 결과와 로그 저장. NAS 예약 작업의 진입점.
- `NETWORK_GUIDE_KO.md`: NAS VPN 게이트웨이 네트워크와 CHECKIN_PROXY 설정 안내.
- `build_release.py`: VERSION에 맞는 공개 파일 ZIP과 SHA256SUMS 생성.
- `.github/workflows/release.yml`: VERSION 변경 시 테스트 후 새 버전의 태그·GitHub 릴리스·배포 파일 게시. 기존 릴리스는 보존.

세션/웹훅은 `.env` 또는 환경변수로 주입합니다. 서버의 `user_points`는 사용 후 남은 잔액입니다. 출석으로 얻은 포인트만의 평생 누적 합계를 계산하지 않습니다.

계정별 `.chrome_profile/<user_id>`를 사용하고, 쿠키의 로그인 계정과 설정된 ID가 다르면 출석하지 않습니다. 이미 완료한 계정도 최신 상태 응답의 잔액을 알립니다. 출석 실패 시에도 계정 식별이 확인된 경우 잔액 조회를 시도합니다.

재빌드 후 배포 절차는 README를 따릅니다. 예전 api.py/main.py만 마운트하는 설정과 혼용하지 않습니다.

## VPN 운영 구성

- `vpn/compose.yml`: Gluetun OpenVPN 게이트웨이와 공개 페이지 진단 서비스.
- `vpn/run-checkin.sh`: 위치 기반 경로 계산·설정 파일 확인·VPN healthy 확인 후 공유 네트워크 실행.
- `vpn/prepare_config.py`: 개인 인라인 설정 변환. 실제 결과는 `vpn/private`에 보관하며 공개 배포에서 제외.
- `diagnose.py`: 계정 정보를 사용하지 않는 공개 접속 테스트와 종료 처리.
- `vpn/README_KO.md`: `/volume1/docker/2dfan-vpn` 운영·기존 폴더 마이그레이션·예약 실행 안내.

일반 설치의 run-scheduler.sh와 VPN 전용 run-checkin.sh를 동시에 예약하지 않습니다. 공개 버전은 v3.0으로 통일했습니다.
