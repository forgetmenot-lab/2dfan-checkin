# STATUS.md — 개발 현황

## 완료된 기능
- [x] 다중 계정 출석체크 (JSON 배열 방식)
- [x] 세션 쿠키 기반 인증
- [x] Cloudflare 통과
- [x] Turnstile 자동 해결 (opencv + nodriver verify_cf)
- [x] 3단계 폴백 전략 구현
- [x] Docker 컨테이너화 (NAS 실행 환경)
- [x] Xvfb 가상 디스플레이 설정
- [x] nodriver 연결 타임아웃 패치
- [x] NAS에서 3개 계정 출석체크 성공 확인 (2026-05-22)

---

## 최근 수정된 파일
| 파일 | 변경 내용 |
|---|---|
| `Dockerfile` | opencv-python-headless, numpy 추가; entrypoint.sh 분리 |
| `entrypoint.sh` | Xvfb 기동 + nodriver 타임아웃 패치 + Strategy 3 스킵 패치 |

---

## 현재 발생 중인 문제
| 문제 | 상태 | 비고 |
|---|---|---|
| Strategy 3 hang | 패치로 스킵 처리 | Docker 환경에서 버튼 클릭 후 tab.evaluate() 무한 대기 |
| Strategy 2 (직접 POST) 422 | NAS에서는 미발생 | 데이터센터 IP에서만 발생. Turnstile 토큰 없이 POST 시 서버 거부 |
| 세션 쿠키 만료 | 미발생(현재) | 주기적 갱신 필요 |

---

## 미완성 기능
- [ ] 출석체크 실패 시 알림 (이메일/텔레그램 등)
- [ ] 세션 쿠키 만료 감지 자동화
- [ ] GitHub Actions 방식 완전 동작 (Turnstile 문제로 보류)

---

## 다음 작업 우선순위
1. Synology 작업 스케줄러 등록 및 자동 실행 검증
2. (선택) 실패 시 알림 기능 추가
3. (선택) 쿠키 만료 감지 로직 추가
