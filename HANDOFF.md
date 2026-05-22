# HANDOFF.md — 다음 AI 세션 인수인계

## 현재 상태 (2026-05-22 기준)
NAS Docker 환경에서 3개 계정 출석체크 **정상 동작 확인**.  
Synology 작업 스케줄러 등록만 하면 자동화 완료.

---

## 테스트 실행 환경
- Synology NAS DS423+ (가정용 IP — Turnstile 자동 해결의 핵심)
- Docker 이미지명: `2dfan-checkin`

## 실행 명령
```bash
sudo docker run --rm --shm-size=256m \
  -v /volume1/docker/2dfan-nas/api.py:/app/api.py \
  -e ACCOUNTS='[{"user_id":"ID","session":"쿠키값"}]' \
  2dfan-checkin
```

---

## 수정 시 주의할 파일

| 파일 | 주의사항 |
|---|---|
| `api.py` | 원본 유지. 런타임 패치는 entrypoint.sh에서 처리 |
| `entrypoint.sh` | Strategy 3 스킵 패치 포함. 제거 시 Docker 환경에서 hang |
| `Dockerfile` | opencv-python-headless 필수. 없으면 verify_cf() 미동작 |

## 건드리면 안 되는 구조
- `api.py`의 `_wait_turnstile()` 로직 — NAS 가정용 IP에서 정상 동작 중
- entrypoint.sh의 Strategy 3 스킵 패치 — Docker에서 필수

---

## 현재 가장 중요한 이슈
**세션 쿠키 만료**: `_project_hgc_session` 값이 만료되면 출석체크 실패.  
증상: 로그에서 버튼이 `None`이거나 Cloudflare 루프 발생.  
조치: 브라우저에서 재로그인 후 쿠키 재추출 → docker run 명령의 ACCOUNTS 값 교체.

---

## 다음 작업 순서
1. **Synology 작업 스케줄러 등록** (최우선)
   - 제어판 → 작업 스케줄러 → 생성 → 사용자 정의 스크립트
   - 사용자: root, 매일 원하는 시간
2. (선택) 실패 알림 기능 — `main.py`에 실패 시 텔레그램/이메일 발송 추가
3. (선택) 쿠키 만료 자동 감지 — 로그 파싱 후 알림

---

## 알려진 제약
- **데이터센터 IP(GitHub Actions)에서는 동작 안 함** — Turnstile 422 반환
- Strategy 2 (`_submit_fetch`)의 async IIFE는 nodriver 0.48.1에서 `None` 반환 (버그)
- Strategy 3은 Docker 환경에서 hang — entrypoint.sh에서 스킵 처리됨
