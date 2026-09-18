# 2dfan Auto Check-in v2.0

NAS Docker에서 2dfan 출석을 처리하고 Discord로 **숫자 ID + 계정명 + 출석 결과 + 현재 보유 포인트**를 알리는 도구입니다.

## 주요 기능

- 세션 쿠키 기반 다중 계정 순차 실행, 로그인 계정 ID 일치 확인
- 리뉴얼된 `/checkin` 페이지와 인증 팝업 처리
- 이미 출석한 계정은 상태·잔액만 조회하고 출석 버튼/인증 생략
- 출석 성공 후 서버에서 포인트를 다시 조회 (출석 보상의 평생 누적 합계가 아닌 현재 잔액)
- 슬라이더로 전환되면 20초 후 페이지를 새로 열어 1회 재시도
- 계정별 실패 분리, Discord 긴 알림 분할 및 전송 오류 처리

슬라이더 인증 자체의 자동 해결은 지원하지 않습니다. 재시도 후에도 인증이 완료되지 않으면 수동 인증이 필요합니다. 사이트 변경이나 네트워크 조건에 따라 자동 출석이 실패할 수 있습니다.

## 준비물

- Docker를 실행할 수 있는 **x86_64 / amd64 NAS** (Intel/AMD)
- Synology 사용 시 해당 모델에서 지원되는 Container Manager 또는 Docker 패키지
- NAS 관리자 계정, SSH 접속용 PC, 2dfan 계정
- 알림을 사용할 경우 Discord 서버와 웹훅 생성 권한

현재 Dockerfile은 Google Chrome amd64 패키지를 설치합니다. Docker가 된다는 이유만으로 ARM NAS까지 지원하는 것은 아닙니다.

## 설치 안내

처음 설치한다면 **[처음부터 따라 하는 설치 가이드](INSTALL_GUIDE_KO.md)**를 읽으세요. GitHub 사용법이나 Git 설치 없이 배포 ZIP만으로 설치할 수 있습니다.

1. `2dfan-auto-checkin-v2.0.zip`을 풀어 내용물을 NAS `/volume1/docker/2dfan-nas/`에 넣습니다.
2. `.env.example`을 `.env`로 복사하고 본인의 계정 쿠키와 Discord 웹훅을 입력합니다.
3. NAS SSH에서 빌드합니다.

```sh
cd /volume1/docker/2dfan-nas
sudo docker build -t 2dfan-checkin .
```

4. 동일한 실행 파일로 수동 테스트합니다.

```sh
sudo /bin/sh /volume1/docker/2dfan-nas/run-scheduler.sh
```

5. Synology 작업 스케줄러의 사용자 `root`, 매일 예약, 실행 명령을 설정합니다.

```sh
/bin/sh /volume1/docker/2dfan-nas/run-scheduler.sh
```

로그: `/volume1/docker/2dfan-nas/scheduler.log`. 스크립트는 로그를 파일로 보내므로 SSH 화면이 조용해도 실행 중일 수 있습니다. 다른 SSH 창에서 `tail -f /volume1/docker/2dfan-nas/scheduler.log`로 확인할 수 있습니다. PC를 켜둘 필요는 없습니다.

## 설정

`.env`의 ACCOUNTS 전체는 한 줄로 작성합니다. 아래 값은 예시이며 실제 인증 정보가 아닙니다.

```dotenv
ACCOUNTS=[{"user_id":"123","session":"COOKIE_1"},{"user_id":"456","session":"COOKIE_2"}]
DISCORD_WEBHOOK=https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN
```

- `user_id`: 프로필 주소 `/users/숫자`의 숫자. 로그인 이름과 다릅니다.
- `session`: 로그인한 브라우저의 `_project_hgc_session` 쿠키 값. `%2F` 등을 디코딩하지 않습니다.
- 계정명은 사이트에서 자동 조회합니다. 선택적인 `name` 설정은 조회 실패 시 표시할 이름입니다.
- 웹훅은 URL 그대로 입력합니다. Markdown 링크나 바깥쪽 작은따옴표를 넣지 않습니다.
- 기존 `DISCORD_WEBHOOK` 및 별칭 `DISCORD_WEBHOOK_URL`을 지원합니다. 알림이 필요 없으면 비워 둡니다.

## 알림 예시

```text
[2dfan 출석체크] 2026-09-18 08:00 KST

✅ 성공
123 · example_user — 출석 성공 · 누적 150일 / 연속 32일
보유 포인트: 103점

⏭ 이미 완료
456 · second_user — 오늘 이미 출석 완료
보유 포인트: 80점
```

잔액은 각 계정 처리 시점 기준이며 Discord 발송 순간 일괄 조회하는 방식은 아닙니다. 조회 불가는 0점 대신 `조회 불가`로 표시합니다. 계정당 최대 360초, 모든 계정 처리 후 알림 전송. 일부 계정 실패 또는 알림 실패 시 종료 코드 1이며 모든 작업이 실패했다는 의미는 아닙니다.

## 기존 설치 업데이트

`.env`를 보존하고 배포 파일을 교체하세요. 첫 구버전에서 업데이트할 때는 반드시 이미지를 재빌드합니다. 이 저장소의 사전 테스트 버전 v3/v4/v5는 정식 버전이 아니며 이번 정식 버전은 **v2.0**입니다.

`run-scheduler.sh`는 `api.py`, `main.py`, `results.py`를 함께 마운트합니다. 예전처럼 api.py만 연결하면 계정명 등 알림 코드가 구버전으로 남을 수 있습니다. 업데이트 후 같은 빌드·테스트 절차를 실행하면 코드와 의존성을 일치시킬 수 있습니다.

## 검증

사용자 NAS 로그에서 실제 출석 성공·완료 후 포인트 증가·스케줄러 실행을 확인했고, 사용자로부터 계정명 알림의 정상 동작을 확인받았습니다. 모든 환경에서 성공을 보장하지 않습니다. 로컬 Docker 엔진이 실행되지 않아 이 환경에서 새 이미지 빌드는 검증하지 못했습니다.

```sh
python -m pip install nodriver==0.48.1 python-dotenv
python -m unittest discover -s tests -v
```

Node.js가 있으면 선택자 JavaScript 테스트도 실행합니다. 자동 테스트는 실제 계정 출석이나 Discord 메시지를 보내지 않습니다.

## 라이선스 및 배포

MIT 라이선스입니다. 원저작자 Ming Wei의 저작권 고지와 LICENSE를 유지합니다. 원본: [WeMingT/2dfan-checkin](https://github.com/WeMingT/2dfan-checkin).

개인 계정 쿠키, `.env`, 웹훅, 로그, 브라우저 프로필을 배포하지 마세요. 배포 ZIP에는 실행 소스·설정 예제·설치 문서·LICENSE만 포함합니다. 사이트의 이용 조건과 권한 범위 안에서 사용하세요. ZIP 직접 배포도 저작권 또는 이용 조건 문제를 없애지는 않습니다.

[변경 사항](CHANGELOG.md) · [설치 안내](INSTALL_GUIDE_KO.md)
