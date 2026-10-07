import asyncio
import json
import logging
import os
import sys
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from api import checkin, browser_options
from results import CheckinResult, format_result
from notify import send_discord

# 抑制 Windows asyncio 管道关闭时的 __del__ 异常
_orig_hook = sys.unraisablehook


def _quiet_hook(args):
    if isinstance(args.exc_value, ValueError) and "closed pipe" in str(args.exc_value):
        return
    _orig_hook(args)


sys.unraisablehook = _quiet_hook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Account:
    user_id: str
    session: str
    name: str = ""


def load_accounts() -> list[Account]:
    accounts_json = os.environ.get("ACCOUNTS")
    if not accounts_json:
        logger.error("请在 .env 中配置 ACCOUNTS")
        sys.exit(1)
    try:
        raw = json.loads(accounts_json)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        accounts = []
        for a in raw:
            user_id, session = str(a["user_id"]), a["session"]
            if not re.fullmatch(r"[0-9]+", user_id) or not isinstance(session, str) or not session.strip():
                raise ValueError
            accounts.append(Account(user_id, session, str(a.get("name", ""))[:100]))
        return accounts
    except (ValueError, KeyError, TypeError):
        raise ValueError("ACCOUNTS는 user_id(숫자)와 session(쿠키)이 있는 JSON 배열이어야 합니다") from None


def _build_message(results: list[tuple[Account, CheckinResult]]) -> list[str]:
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    lines = [f"**[2dfan 출석체크] {now}**"]
    groups = [("✅ 성공", lambda r: not r.error and not r.already_done),
              ("⏭ 이미 완료", lambda r: not r.error and r.already_done),
              ("❌ 실패", lambda r: bool(r.error))]
    for heading, matches in groups:
        entries = [(a, r) for a, r in results if matches(r)]
        if entries:
            lines.append(heading)
            for acc, result in entries:
                # Prefer the site's account name; a configured name is a fallback
                # when login/display metadata is unavailable.
                name = " ".join((result.account_name or acc.name or "계정명 조회 불가").split())[:100]
                name = "".join("\\" + c if c in "\\`*_~|<>[]" else c for c in name)
                label = f" · {name}" if name else ""
                lines.append(f"`{acc.user_id}`{label} — {format_result(result)}")
    return lines


async def main():
    logger.info("2dfan-checkin v3.0: NAS VPN 네트워크 및 브라우저 프록시 지원")
    load_dotenv()
    try:
        browser_options()
        accounts = load_accounts()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    logger.info("브라우저 접속 경로: %s", "명시적 프록시" if os.environ.get("CHECKIN_PROXY", "").strip()
                else "기본 네트워크 (VPN 사용 여부는 실행 환경에서 확인 필요)")
    logger.info("共 %d 个账号待签到", len(accounts))
    results: list[tuple[Account, CheckinResult]] = []
    for i, acc in enumerate(accounts, 1):
        logger.info("── 账号 %d/%d (ID: %s) ──", i, len(accounts), acc.user_id)
        try:
            result = await asyncio.wait_for(checkin(acc.user_id, acc.session), timeout=360)
        except TimeoutError:
            result = CheckinResult(error="계정 처리 시간 초과 (360초)")
        except Exception as exc:
            result = CheckinResult(error=f"계정 처리 오류 ({type(exc).__name__})")
        if result.error:
            for account in accounts:
                result.error = result.error.replace(account.session, "[redacted]")
        logger.info("[%s] %s", acc.user_id, format_result(result))
        results.append((acc, result))

    lines = _build_message(results)
    for acc in accounts:
        lines = [line.replace(acc.session, "[redacted]") for line in lines]
    # Preserve the NAS setting; accept the alternative name for compatibility.
    webhook = os.environ.get("DISCORD_WEBHOOK", "").strip() or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    notified = await asyncio.to_thread(send_discord, webhook, lines)
    return 1 if any(r.error for _, r in results) or not notified else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
