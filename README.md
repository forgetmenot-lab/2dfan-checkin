# 2dfan 자동 출석체크

2dfan.com 다중 계정 자동 출석체크 도구.  
NAS Docker 환경에서 실행. 가정용 IP 필수 (Cloudflare Turnstile 자동 해결).

## 파일 구조
- `main.py` — [WeMingT 원본](https://github.com/WeMingT/2dfan-checkin) 사용
- `api.py` — [WeMingT 원본](https://github.com/WeMingT/2dfan-checkin) 사용
- `Dockerfile` — 최적화된 Docker 이미지
- `entrypoint.sh` — 컨테이너 시작 스크립트

## 설치 및 실행

자세한 내용은 `PROJECT.md` 참고.

```bash
sudo docker build -t 2dfan-checkin .
sudo docker run --rm --shm-size=256m \
  -v $(pwd)/api.py:/app/api.py \
  -e ACCOUNTS='[{"user_id":"ID","session":"쿠키값"}]' \
  2dfan-checkin
```

## 문서
- [PROJECT.md](PROJECT.md) — 전체 구조 및 아키텍처
- [STATUS.md](STATUS.md) — 개발 현황
- [HANDOFF.md](HANDOFF.md) — AI 인수인계 메모
