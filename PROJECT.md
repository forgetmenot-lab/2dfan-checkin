# PROJECT.md — 2dfan 자동 출석체크

## 프로젝트 목적
2dfan.com 다중 계정 자동 출석체크.  
세션 쿠키 기반으로 Chrome을 자동화해 Cloudflare + Turnstile을 통과하고 출석체크 버튼을 클릭한다.

---

## 기술 스택
| 항목 | 내용 |
|---|---|
| 언어 | Python 3.12 |
| Chrome 자동화 | nodriver 0.48.1 |
| 실행 환경 | Docker (NAS) |
| 패키지 관리 | pip (nodriver, python-dotenv, opencv-python-headless, numpy) |
| 스케줄 | Synology 작업 스케줄러 |

---

## 디렉토리 구조
```
2dfan-checkin/
├── main.py           # 진입점. ACCOUNTS 파싱 후 계정별 checkin() 호출
├── api.py            # 핵심 로직. Chrome 자동화 + 출석체크 3단계 전략
├── Dockerfile        # Docker 이미지 빌드 (Chrome + Xvfb + 최소 패키지)
├── entrypoint.sh     # 컨테이너 시작 스크립트. Xvfb 기동 + 런타임 패치 적용
├── PROJECT.md
├── STATUS.md
└── HANDOFF.md
```

---

## 핵심 파일 설명

### main.py
- 환경변수 `ACCOUNTS`(JSON 배열)를 읽어 각 계정에 대해 `api.checkin()` 순차 실행
- 결과를 로그로 출력

### api.py
- `checkin(user_id, session_cookie)` : 출석체크 메인 함수
- Chrome 시작 → 세션 쿠키 주입 → 페이지 이동 → Cloudflare 통과 → 출석체크
- **3단계 폴백 전략**:
  1. `_wait_turnstile()` → Turnstile 자동 해결 → `_submit_normal()` (버튼 클릭)
  2. `_submit_fetch()` → 직접 fetch POST (Turnstile 해결 실패 시)
  3. `_submit_no_captcha()` → captcha DOM 제거 후 버튼 클릭

### Dockerfile
- python:3.12-slim 기반
- Google Chrome stable + Xvfb + opencv-python-headless 포함
- entrypoint.sh를 ENTRYPOINT로 지정

### entrypoint.sh
- Xvfb :99 기동 후 `DISPLAY=:99` 설정
- 런타임 패치 적용:
  - nodriver 연결 타임아웃 연장 (`range(5)` → `range(20)`)
  - Chrome `--disable-gpu`, `--disable-software-rasterizer` 플래그 추가
  - Strategy 3(`_submit_no_captcha`) 스킵 (Docker 환경에서 hang 발생)
- `python main.py` 실행

---

## 인증 방식
- 이메일/비밀번호 로그인 없음
- 브라우저 쿠키 `_project_hgc_session` 값을 직접 Chrome에 주입
- `user_id`: 프로필 URL `https://2dfan.com/users/{숫자}` 의 숫자

## 계정 설정 (환경변수)
```json
ACCOUNTS=[{"user_id":"123","session":"쿠키값"},{"user_id":"456","session":"쿠키값"}]
```

---

## 아키텍처 요약
```
[Synology 작업 스케줄러]
        ↓ 매일 지정 시간
[docker run 명령]
        ↓
[Docker 컨테이너]
  entrypoint.sh
    → Xvfb 기동
    → 런타임 패치
    → python main.py
        → api.checkin() × N계정
            → Chrome (가정용 IP)
            → 2dfan.com Turnstile 자동 해결 (1초)
            → 출석체크 완료
```

---

## 주의사항
- **세션 쿠키 만료** 시 docker run 명령의 ACCOUNTS 값 수정 필요 (주기: 수주~수개월 추정)
- entrypoint.sh의 패치는 **런타임에만 적용**됨. api.py 원본은 변경 없음
- `-v /volume1/docker/2dfan-nas/api.py:/app/api.py` 볼륨 마운트 사용 시 이미지 재빌드 없이 api.py 수정 가능
- Docker 이미지 크기: 약 700MB (opencv-python-headless 포함)
- NAS 가정용 IP 필수 — 데이터센터 IP(GitHub Actions 등)에서는 Turnstile이 해결되지 않아 422 반환
