# NAS VPN·프록시 설정 (v3.0)

기존 출석 로직을 유지하면서 NAS의 실제 VPN 연결 또는 명시적인 브라우저 프록시를 사용할 수 있습니다. **카스퍼스키 OpenVPN으로 출석 컨테이너만 연결하려면 [전용 설치 안내](vpn/README_KO.md)를 따르세요.** DS423+에서 VPN 연결·공개 페이지 접속·로그인 상태 조회와 DDNS 유지가 확인됐습니다. 실제 자동 출석 제출과 터널 단절 차단은 별도 검증이 필요합니다. 계정 잠금 안내가 발견되면 해당 계정의 출석을 중단하고 실패 알림을 보냅니다. 관리자에게 잠금 해제를 받은 뒤 새 로그인 세션으로 실행하세요.

PC에서 켠 카스퍼스키 VPN과 오페라의 무료 내장 VPN은 NAS 컨테이너에 자동 적용되지 않습니다. NAS에서 사용할 수 있는 VPN 구성 또는 프록시 주소가 필요합니다. 현재 카스퍼스키 계약으로 NAS 연결이 가능한지는 제공받은 구성과 NAS 모델에 따라 별도 확인해야 합니다.

## 1. NAS 자체가 VPN으로 연결된 경우

NAS에서 VPN을 연결하고, Docker 컨테이너의 인터넷 연결도 해당 VPN을 사용하는지 확인하세요. NAS 연결만으로 컨테이너 경로까지 보장되지는 않습니다. `.env`의 `CHECKIN_PROXY`는 비워 두고 기존 스케줄러를 실행합니다.

```sh
/bin/sh /volume1/docker/2dfan-nas/run-scheduler.sh
```

## 2. 이미 실행 중인 VPN 게이트웨이 컨테이너가 있는 경우

아래 `my-vpn`을 실제 VPN 컨테이너 이름으로 바꿉니다. 실행 명령과 NAS 작업 스케줄러에 같은 설정을 사용합니다.

```sh
CHECKIN_DOCKER_NETWORK=container:my-vpn /bin/sh /volume1/docker/2dfan-nas/run-scheduler.sh
```

`CHECKIN_DOCKER_NETWORK`는 `docker run`을 실행하는 셸의 환경변수입니다. **`.env`에만 적으면 run-scheduler.sh에는 적용되지 않습니다.** NAS 작업 스케줄러의 실행 명령을 위와 같이 바꾸세요. run-nas.sh도 같은 셸 환경변수를 지원합니다.

Docker Compose를 쓰는 경우에는 `.env`에 다음을 추가할 수 있습니다. 게이트웨이가 이미 실행 중이어야 합니다.

```dotenv
CHECKIN_DOCKER_NETWORK=container:my-vpn
CHECKIN_PROXY=
```

```sh
docker compose run --rm 2dfan-checkin
```

VPN 컨테이너가 없거나 중지된 경우 실행이 실패합니다. 기본 bridge로 자동 재시도하지 않습니다. VPN 터널이 끊겼을 때 일반 인터넷으로 연결되지 않도록 하는 기능은 VPN 게이트웨이에서 설정해야 합니다. 이 프로그램은 VPN의 활성 상태나 출구 국가를 자동 확인하지 않습니다.

## 3. NAS 컨테이너에서 연결 가능한 프록시가 있는 경우

`.env`에 실제 주소를 입력합니다. 아래 주소는 예시입니다.

```dotenv
CHECKIN_PROXY=http://192.168.1.20:8080
```

또는:

```dotenv
CHECKIN_PROXY=socks5://192.168.1.20:1080
```

`http`, `https`, `socks5`를 지원합니다. 호스트와 포트가 필요하고 사용자명·비밀번호가 포함된 주소는 지원하지 않습니다. Chrome의 SOCKS5는 인증을 지원하지 않습니다. 인증이 필요한 서비스라면 적절히 보호된 VPN 게이트웨이/로컬 프록시를 별도로 구성해야 합니다.

컨테이너의 `127.0.0.1`은 기본적으로 NAS나 PC가 아닌 **컨테이너 자신**입니다. PC 주소를 사용하는 프록시는 그 PC가 켜져 있어야 하므로 NAS 독립 운용이 되지 않습니다.

프록시 설정은 출석 브라우저에 적용됩니다. 상태 조회와 프로필 조회도 같은 브라우저 안에서 수행됩니다. Discord 알림은 Python에서 전송하므로 이 설정이 적용되지 않습니다. 전체 컨테이너가 VPN 경로를 쓰면 알림도 그 경로를 사용합니다.

## 업데이트 및 확인

기존 `.env`를 보존한 상태로 v3.0 파일을 교체하고 이미지를 다시 빌드합니다.

```sh
cd /volume1/docker/2dfan-nas
sudo docker build -t 2dfan-checkin .
```

위에서 선택한 실행 명령으로 수동 실행한 뒤 `scheduler.log`를 확인하세요. 시작 로그에 브라우저 프록시 지정 여부가 표시됩니다. 계정 잠금, Cloudflare 차단 페이지, 브라우저에 표시된 프록시·DNS 연결 오류를 구분해 보고합니다. 기본 네트워크 로그는 VPN 활성 확인을 의미하지 않습니다. 브라우저 시작/이동 단계에서 예외가 발생하면 일반 처리 오류로 나올 수도 있습니다.

실제 NAS/VPN 접속과 출석은 사용 환경에서 별도 확인해야 합니다. 접속 성공만으로 한국 전체 차단 여부나 과거 계정 정지 원인을 확정할 수 없습니다.

설정 근거: [Chromium 프록시 설정](https://www.chromium.org/developers/design-documents/network-settings/), [SOCKS5와 인증 제한](https://github.com/chromium/chromium/blob/main/net/docs/proxy.md), [Opera VPN 안내](https://help.opera.com/en/latest/security-and-privacy/).
