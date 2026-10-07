# NAS VPN 전용 설치·운영 가이드 — v3.0

출석 컨테이너만 Gluetun OpenVPN 게이트웨이의 네트워크를 사용합니다. NAS의 기본 게이트웨이나 DDNS 설정은 변경하지 않습니다. PC는 최초 설정과 세션 갱신 때만 필요하며 예약 실행은 NAS가 담당합니다.

```text
NAS 관리·DDNS·공유 폴더 → 기존 NAS 네트워크
출석 컨테이너 → 2dfan-vpn(Gluetun) → VPN 서버 → 2dfan / Discord
```

VPN Server 패키지는 외부에서 NAS로 접속하는 서버 기능이며 이 구성에 필요하지 않습니다. DSM 전체 VPN을 켜면 DDNS 연결에 영향을 줄 수 있으므로 이 방식과 함께 사용하지 않습니다. 포트 공개나 host 네트워크를 추가하지 않습니다.

## 1. 준비물과 파일 배치

Docker/Container Manager를 지원하는 amd64 NAS, 관리자 SSH 접근, VPN 제공업체의 OpenVPN 파일과 전용 인증 정보가 필요합니다. Kaspersky Plus에서 발급받은 구성으로 테스트했지만 NAS 공식 지원·라이선스 조건은 본인의 구독과 업체 안내를 확인해야 합니다. 테스트 당시 1기기 VPN 구독은 PC VPN 앱과 설정 파일을 동시에 프리미엄으로 사용할 수 없었습니다.

배포 ZIP의 `2dfan-nas` 내부 파일을 File Station으로 `/volume1/docker/2dfan-vpn`에 업로드합니다. ZIP 최상위 폴더 이름은 기존 기본 설치와의 호환을 위해 `2dfan-nas`이며 VPN 운영 폴더 이름과는 별개입니다.

```text
/volume1/docker/2dfan-vpn/
  .env                       # 출석 계정 세션·Discord 웹훅
  Dockerfile / diagnose.py / api.py / main.py / ...
  vpn/
    compose.yml
    run-checkin.sh
    prepare_config.py
    vpn.env.example
    private/
      custom.conf            # VPN 인증서·개인키를 포함하는 개인 파일
      vpn.env                # OpenVPN 전용 사용자명·비밀번호
    state/                   # Gluetun 상태 저장, 시작 전 생성
```

실제 `.env`, `custom.conf`, `vpn.env`, 로그와 개인키는 GitHub·공개 ZIP에 포함하지 않습니다.

## 2. OpenVPN 설정 준비

My Kaspersky에서 OpenVPN 설정 파일과 그 설정에 대한 사용자명·비밀번호를 확보합니다. PC의 VPN 앱 로그아웃 후 설정 발급 메뉴가 나타날 수 있다는 지원 안내가 있었습니다. 메뉴와 절차는 구독 상태에 따라 달라질 수 있습니다. NAS의 DSM VPN 프로필에서 이미 사용한 것과 같은 전용 인증 정보를 사용하며 My Kaspersky 계정 비밀번호가 아닙니다.

PC에 Python 3.10 이상이 있다면 압축을 푼 프로젝트 루트에서 아래 명령을 실행합니다.

```sh
python vpn/prepare_config.py credentials.ovpn vpn/private/custom.conf
```

원본의 인라인 인증서·키를 유지하고 Windows 전용 `route-method`를 제거하며 `remote`의 호스트명을 IPv4로 변환합니다. Gluetun의 시작 방화벽 때문에 서버 주소를 먼저 해석해야 합니다. 이 준비 단계에서만 PC DNS를 사용합니다. 서버 주소가 바뀌면 원본으로 다시 생성하세요. 외부 인증서 파일을 참조하거나 스크립트를 실행하는 구성은 이 변환 도구가 지원하지 않습니다.

생성한 `custom.conf`를 NAS의 `vpn/private`로 업로드합니다. 이미 준비한 개인 파일이 있으면 재사용할 수 있습니다. `vpn/vpn.env.example`을 `vpn/private/vpn.env`로 복사한 뒤 다음을 수정합니다.

```dotenv
OPENVPN_USER='발급받은 OpenVPN 사용자명'
OPENVPN_PASSWORD='발급받은 OpenVPN 비밀번호'
```

이 파일은 **Compose env_file** 형식입니다. 작은따옴표는 값에서 제거되고 `$` 등이 문자 그대로 전달됩니다. 실제 값에 작은따옴표가 들어 있다면 Compose의 따옴표 규칙에 맞게 작성하세요. 예시 `REPLACE_WITH_...` 값이 남아 있으면 인증에 실패합니다.

## 3. VPN 시작과 공개 페이지 테스트

PC에서 자신의 NAS 주소·사용자·SSH 포트로 로그인합니다. 비밀번호는 SSH 프롬프트에 입력합니다.

```sh
ssh -p SSH_PORT NAS_USER@NAS_IP
```

NAS에서:

```sh
cd /volume1/docker/2dfan-vpn
mkdir -p vpn/private vpn/state
chmod 700 vpn/private
chmod 600 vpn/private/custom.conf vpn/private/vpn.env
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml config --quiet
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml up -d vpn
sudo docker inspect --format '{{.State.Health.Status}}' 2dfan-vpn
```

`starting`이면 잠시 기다린 뒤 상태를 다시 확인합니다. `unhealthy`이면 아래 로그부터 확인하세요. `AUTH_FAILED`는 VPN 서버가 인증을 거부한 것이므로 전용 사용자명·비밀번호, 설정의 유효 상태, 예시 값 잔존 여부를 확인합니다. 인증 파일을 수정한 후에는 컨테이너를 재생성해야 합니다.

```sh
sudo docker logs --tail 60 2dfan-vpn
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml up -d --force-recreate vpn
```

상태가 `healthy`이면:

```sh
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml build probe
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml run --rm probe
echo "종료 코드: $?"
```

최초 빌드는 몇 분 걸릴 수 있습니다. 테스트는 로그인 쿠키를 읽거나 출석을 제출하지 않고 VPN 출구 IP/국가와 2dfan 공개 페이지 상태를 출력합니다. `challenge`는 챌린지 대기, `blocked`는 차단 안내, `network`는 브라우저 연결 오류입니다. 코드 0은 공개 페이지 내용 확인, 2는 차단/챌린지/내용 확인 실패, 1은 실행 오류입니다. 정리 단계의 경고는 공개 페이지 접속 판정과 분리합니다.

선택한 지역과 IP 위치 데이터베이스의 국가가 다를 수 있으므로 출력된 국가도 확인하세요. 테스트에서는 상하이로 발급한 구성이 US로 판정됐습니다. NAS의 DDNS와 네트워크 드라이브 연결이 유지되는지도 확인합니다.

## 4. 출석용 .env와 세션

최상위 `.env.example`을 **`.env`**로 복사합니다. `env`나 `.env.txt`라는 이름은 사용할 수 없습니다. 이 파일은 Docker의 **--env-file** 형식으로 읽습니다. `=` 앞뒤 공백과 값 전체를 감싼 따옴표를 넣지 마세요. JSON 내부 따옴표는 유지하며 ACCOUNTS 전체는 한 줄로 씁니다.

```dotenv
ACCOUNTS=[{"user_id":"123456","session":"실제 세션 쿠키 값"}]
DISCORD_WEBHOOK=https://discord.com/api/webhooks/실제ID/실제토큰
CHECKIN_PROXY=
```

알림이 필요 없으면 DISCORD_WEBHOOK을 비웁니다. 오페라에서 VPN을 켜고 정상 로그인한 뒤 `Ctrl+Shift+I` → Application → Storage → Cookies → `https://2dfan.com`에서 `_project_hgc_session`의 **Value 전체**를 복사합니다. 쿠키 이름이나 `=`는 붙이지 않습니다. user_id는 본인 프로필 URL의 숫자입니다. 계정이 잠긴 상태라면 먼저 관리자에게 해제를 요청해야 합니다.

VPN용 `vpn/private/vpn.env`와 출석용 `.env`는 경로·역할·읽는 방식이 다르므로 혼용하지 않습니다. 쿠키·웹훅·VPN 인증 정보는 로그나 채팅에 공유하지 않습니다.

## 5. 수동 실행과 예약

```sh
cd /volume1/docker/2dfan-vpn
ls -la .env
chmod 600 .env
sudo /bin/sh vpn/run-checkin.sh
```

스크립트는 자신의 위치에서 프로젝트 루트를 계산하고 VPN 정상 상태를 최대 60초 기다립니다. `healthy`일 때만 `--network container:2dfan-vpn`으로 출석 컨테이너를 실행하며 일반 네트워크로 재시도하지 않습니다. 브라우저의 `기본 네트워크` 로그는 별도 프록시가 없다는 뜻이며 실행 스크립트가 선택한 VPN 공유 네트워크를 부정하지 않습니다. 실행 중의 터널 단절 차단은 Gluetun 방화벽이 담당하며 방화벽을 켜 둡니다. 실제 단절 차단 테스트는 아직 미완료입니다.

슬라이더가 나오면 20초 후 같은 브라우저·세션으로 페이지를 다시 열어 한 번 재시도합니다. 최대 2회 후에도 슬라이더가 나오면 중단하며 슬라이더 자동 해결·무제한 재접속·VPN IP 변경을 하지 않습니다. `오늘 이미 출석 완료`는 상태 조회 성공이며 이번 실행의 자동 제출 성공을 뜻하지 않습니다.

수동 확인 후 기존 출석 예약을 비활성화하고 DSM 작업 스케줄러에서 root 사용자 작업을 매일 원하는 시간으로 설정합니다.

```sh
/bin/sh /volume1/docker/2dfan-vpn/vpn/run-checkin.sh >> /volume1/docker/2dfan-vpn/vpn-checkin.log 2>&1
```

로그 확인:

```sh
tail -n 80 /volume1/docker/2dfan-vpn/vpn-checkin.log
```

## 6. 기존 2dfan-vpn-test 폴더 정리

기존 Compose 프로젝트명 `2dfan-vpn-test`로 운영하던 설치는 프로젝트명을 유지합니다. VPN 컨테이너의 마운트 경로를 갱신해야 하므로 실행 중 폴더만 이름 변경하지 않습니다.

```sh
cd /volume1/docker/2dfan-vpn-test
sudo docker compose -p 2dfan-vpn-test -f vpn/compose.yml down
cd /volume1/docker
mv -i 2dfan-vpn-test 2dfan-vpn
cd /volume1/docker/2dfan-vpn
sudo docker compose -p 2dfan-vpn-test -f vpn/compose.yml up -d vpn
```

각 명령의 성공을 확인한 뒤 다음으로 넘어갑니다. `cd`가 실패하면 이전 위치에 그대로 있으므로 이후 명령을 실행하지 마세요. 상태가 healthy인지 확인하고 스케줄러의 실행 경로와 로그 경로를 **모두** `2dfan-vpn`으로 변경합니다. 이후 이 가이드의 Compose 명령에서도 `-p 2dfan-vpn-test`를 사용합니다. 신규 설치는 `-p 2dfan-vpn`을 사용합니다.

예전 `2dfan-nas`는 필요한 설정을 옮기고 기존 예약 작업·마운트 의존성이 없음을 확인한 후 정리합니다. `vpn/private`와 `vpn/state`는 유지합니다.

## 7. 중지와 업데이트

```sh
cd /volume1/docker/2dfan-vpn
sudo docker compose -p 2dfan-vpn -f vpn/compose.yml down
```

기존 프로젝트명이 `2dfan-vpn-test`면 위 명령의 -p도 기존 이름을 사용합니다. 코드 업데이트 시 `.env`, `vpn/private`, `vpn/state`를 보존하고 공개 파일을 교체한 뒤 `build probe`로 이미지를 재빌드합니다. PC 프리미엄 VPN으로 돌아가는 설정 해제 절차는 VPN 업체 지원 안내를 따릅니다.

구성 근거: [Gluetun 사용자 OpenVPN 설정](https://github.com/qdm12/gluetun-wiki/blob/main/setup/openvpn-configuration-file.md), [VPN 네트워크 공유](https://github.com/qdm12/gluetun-wiki/blob/main/setup/connect-a-container-to-gluetun.md).
