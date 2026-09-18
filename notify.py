"""Discord summaries using the standard library; no webhook tokens in logs."""

import json
import logging
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def message_chunks(lines: list[str], limit: int = 1900) -> list[str]:
    # Count UTF-16 units conservatively, including emoji in account names.
    chunks, chunk, size = [], "", 0
    for char in "\n\n".join(lines):
        units = len(char.encode("utf-16-le")) // 2
        if size + units > limit:
            chunks.append(chunk)
            chunk, size = "", 0
        chunk += char
        size += units
    if chunk:
        chunks.append(chunk)
    return chunks


def send_discord(webhook_url: str, lines: list[str]) -> bool:
    if not webhook_url:
        logger.info("DISCORD_WEBHOOK 미설정: 로그로만 결과 출력")
        return True
    try:
        parts = urlsplit(webhook_url)
    except ValueError:
        logger.error("Discord 웹훅 URL 형식이 올바르지 않습니다")
        return False
    if (parts.scheme != "https" or parts.hostname not in {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
            or not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]+", parts.path)):
        logger.error("Discord 웹훅 URL 형식이 올바르지 않습니다")
        return False
    query = dict(parse_qsl(parts.query))
    query["wait"] = "true"
    url = urlunsplit(parts._replace(query=urlencode(query)))
    for chunk in message_chunks(lines):
        body = json.dumps({"content": chunk, "allowed_mentions": {"parse": []}}, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "2dfan-checkin/2"}, method="POST")
        for attempt in range(3):
            try:
                with urlopen(request, timeout=20) as response:
                    if not 200 <= response.status < 300:
                        logger.error("Discord 전송 실패 (HTTP %s)", response.status)
                        return False
                break
            except HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    try:
                        delay = float(json.loads(exc.read()).get("retry_after", 1))
                    except (ValueError, TypeError, AttributeError):
                        delay = 1
                    if 0 <= delay <= 60:
                        time.sleep(delay)
                        continue
                logger.error("Discord 전송 실패 (HTTP %s)", exc.code)
                return False
            except (URLError, TimeoutError, OSError):
                logger.error("Discord 연결 실패: 웹훅 설정과 네트워크를 확인하세요")
                return False
    return True
