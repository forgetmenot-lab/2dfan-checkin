"""2dfan.com 签到模块 — 使用 nodriver 自动化 Chrome 完成签到。

流程：启动 Chrome → 设置 cookie → 通过 Cloudflare → 打开签到弹窗
→ 通过 Turnstile → 提交签到 → 读取签到状态。

2DFan v2.0 (2026) 将签到页从 ``/users/:id/recheckin`` 移到了
``/checkin``，并用 Vue 弹窗替代了旧的 ``#do_checkin`` 表单。
"""

import json
import logging
import os
import re
import asyncio
from urllib.parse import urlparse

import nodriver as uc
from results import CheckinResult, parse_balance

logger = logging.getLogger(__name__)

_CF_TITLES = ["Just a moment", "请稍候"]
_CHROME_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chrome_profile")
_CHECKIN_URL = "https://2dfan.com/checkin"

# 获取按钮状态的 JS
_BTN_STATE_JS = """
(() => {
    function visible(e) { return !!(e && e.getClientRects().length); }
    document.querySelectorAll('[data-checkin-automation="action"]').forEach(e => e.removeAttribute('data-checkin-automation'));
    var root = document.querySelector('[data-island="NexusCheckin"]') || document.getElementById('checkin');
    if (!root) return null;
    var b = Array.from(root.querySelectorAll('#do_checkin, .checkin-action button')).find(visible);
    if (!b) {
        b = Array.from(root.querySelectorAll('button')).find(function(e) {
            return visible(e) && ['签到', '立即签到', '今日签到', '今日已签到', '今天已签到', '冷却中'].includes(e.textContent.trim());
        });
    }
    if (!b) return null;
    b.setAttribute('data-checkin-automation', 'action');
    return JSON.stringify({
        text: b.textContent.trim(),
        cls: b.className,
        disabled: b.disabled || b.getAttribute('aria-disabled') === 'true'
    });
})()
"""

_CONFIRM_STATE_JS = """
(() => {
    function visible(e) { return !!(e && e.getClientRects().length); }
    document.querySelectorAll('[data-checkin-automation="confirm"]').forEach(e => e.removeAttribute('data-checkin-automation'));
    var body = document.querySelector('.captcha-modal-body');
    var root = body && (body.closest('[role="dialog"], .n-card') || body.parentElement);
    if (!root) return null;
    var b = Array.from(root.querySelectorAll('button')).find(function(e) {
        return visible(e) && ['确认', '确认签到'].includes(e.textContent.trim());
    });
    if (!b) return null;
    b.setAttribute('data-checkin-automation', 'confirm');
    return JSON.stringify({text: b.textContent.trim(), disabled: b.disabled});
})()
"""


_STATUS_JS = """
(async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetch('/checkin/status.json', {
            credentials: 'same-origin', cache: 'no-store',
            headers: {'Accept': 'application/json'}, signal: controller.signal
        });
        if (!response.ok) return JSON.stringify({http_error: response.status});
        return JSON.stringify(await response.json());
    } catch (_) {
        return JSON.stringify({http_error: 'network'});
    } finally { clearTimeout(timer); }
})()
"""

_IDENTITY_JS = """
(() => {
    const e = document.querySelector('[data-island="NexusCheckin"]');
    if (!e) return null;
    try { return String(JSON.parse(e.getAttribute('data-props')).currentUserId); }
    catch (_) { return null; }
})()
"""

# Diagnostic flags only: never return CAPTCHA tokens, cookies or page HTML.
_CAPTCHA_STATE_JS = """
(() => {
    const body = document.querySelector('.captcha-modal-body');
    const visible = e => !!(e && e.getClientRects().length);
    return JSON.stringify({
        modal: visible(body),
        turnstile: !!(body && body.querySelector('input[name="cf-turnstile-response"], iframe[src*="challenges.cloudflare.com"]')),
        token_ready: !!(body && body.querySelector('input[name="cf-turnstile-response"]')?.value),
        slider: !!(body && body.querySelector('[id^="aliyun-captcha-"]'))
    });
})()
"""


async def _captcha_state(tab) -> dict:
    raw = await tab.evaluate(_CAPTCHA_STATE_JS)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


async def _read_status(tab) -> dict:
    raw = await tab.evaluate(_STATUS_JS, await_promise=True)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError("출석 상태 응답을 읽지 못했습니다") from None
    if not isinstance(data, dict) or not isinstance(data.get("checked"), bool):
        raise RuntimeError("출석 상태 조회 실패: 로그인 상태와 사이트 응답을 확인하세요")
    return data


def _result_from_status(status: dict, *, already_done=False) -> CheckinResult:
    return CheckinResult(
        checkins_count=_counter(status.get("checkins_count")),
        serial_checkins=_counter(status.get("serial_checkins")),
        points=parse_balance(status.get("user_points")),
        already_done=already_done,
    )


# ── Cloudflare 挑战处理 ───────────────────────────────────────────


async def _on_cf_challenge(tab) -> bool:
    try:
        title = await tab.evaluate("document.title")
        return any(kw in (title or "") for kw in _CF_TITLES)
    except Exception:
        return True


async def _pass_cf_challenge(tab, timeout: int = 90) -> bool:
    for sec in range(timeout):
        if not await _on_cf_challenge(tab):
            logger.info("Cloudflare 验证通过（%d 秒）", sec)
            return True
        if sec % 10 == 0:
            logger.info("等待 Cloudflare 验证... (%d/%ds)", sec, timeout)
        await tab.sleep(1)
    return False


# ── 页面状态检测 ──────────────────────────────────────────────────


async def _get_btn_state(tab) -> dict | None:
    raw = await tab.evaluate(_BTN_STATE_JS)
    if not raw:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


async def _check_already_done(tab) -> bool:
    """检查新旧签到面板是否显示已签到。"""
    state = await _get_btn_state(tab)
    return bool(state and state.get("text") in {"今日已签到", "今天已签到"})


async def _get_confirm_state(tab) -> dict | None:
    raw = await tab.evaluate(_CONFIRM_STATE_JS)
    if not raw:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


def _counter(value) -> int:
    return int(value) if not isinstance(value, bool) and re.fullmatch(r"[0-9]+", str(value)) else -1


class SliderChallengeError(RuntimeError):
    """The site switched to a slider before submission."""


async def _submit_normal(tab) -> None:
    """Click only the daily action and its CAPTCHA confirmation, never calendar cells."""
    await _get_btn_state(tab)
    btn = await tab.query_selector('[data-checkin-automation="action"]')
    if not btn:
        raise ValueError("출석 버튼이 사라졌습니다")
    logger.info("출석 버튼 클릭: 인증 팝업/직접 출석 응답 대기")
    await btn.click()
    confirmed = False
    attempts = 0
    ready_polls = 0
    last_attempt = -10
    previous_state = None
    slider_polls = 0
    last_stage = "인증 팝업 또는 출석 응답을 찾지 못했습니다"
    for poll in range(60):
        if await _check_already_done(tab):
            logger.info("화면에서 출석 완료 확인: 서버 상태 재조회")
            return
        # Vue enables this button only after either supported CAPTCHA has completed.
        confirm_state = await _get_confirm_state(tab)
        captcha = await _captcha_state(tab)
        state = (bool(captcha.get("modal")), bool(confirm_state),
                 confirm_state.get("disabled") if confirm_state else None,
                 bool(captcha.get("turnstile")), bool(captcha.get("token_ready")),
                 bool(captcha.get("slider")), confirmed)
        if state != previous_state or poll % 10 == 0:
            logger.info("인증 상태: 팝업=%s 확인버튼=%s 비활성=%s Cloudflare요소=%s 토큰발급=%s 슬라이더=%s 제출=%s", *state)
            previous_state = state
        if not captcha.get("slider"):
            slider_polls = 0
        if captcha.get("slider"):
            last_stage = "슬라이더 인증으로 전환되어 자동 인증을 완료하지 못했습니다"
            if not confirmed and (not confirm_state or confirm_state.get("disabled")):
                slider_polls += 1
                if slider_polls >= 3:
                    latest = await _read_status(tab)
                    if latest["checked"]:
                        return
                    raise SliderChallengeError(last_stage)
            else:
                slider_polls = 0
        elif captcha.get("modal") and not confirm_state:
            last_stage = "인증 팝업의 확인 버튼을 찾지 못했습니다"
        if confirm_state and not confirmed:
            if not confirm_state.get("disabled"):
                confirm = await tab.query_selector('[data-checkin-automation="confirm"]')
                if confirm:
                    logger.info("인증 완료: 확인 버튼 클릭, 출석 제출")
                    await confirm.click()
                    confirmed = True
                    last_stage = "인증 후 확인 버튼을 눌렀지만 출석 완료 응답이 없습니다"
            elif not captcha.get("slider"):
                last_stage = "Cloudflare 인증이 완료되지 않아 확인 버튼이 비활성 상태입니다"
                # The modal can render before the checkbox. Do not consume our
                # only attempt during the opening animation; retry boundedly.
                ready_polls += 1
                if ready_polls < 3 or poll - last_attempt < 2 or attempts >= 3:
                    await tab.sleep(1)
                    continue
                attempts += 1
                last_attempt = poll
                logger.info("Cloudflare 체크박스 처리 시도 %d/3", attempts)
                try:
                    await asyncio.wait_for(tab.verify_cf(), timeout=15)
                    logger.info("체크박스 클릭 보조 종료: 실제 인증 완료 여부는 확인 버튼으로 판정")
                except Exception as exc:
                    logger.warning("체크박스 처리 실패 (%s)", type(exc).__name__)
        else:
            ready_polls = 0
        error = await tab.evaluate("document.querySelector('.checkin-error')?.innerText || ''")
        if error:
            raise RuntimeError("사이트가 출석 요청을 거부했습니다: 인증 또는 쿨다운 상태를 확인하세요")
        await tab.sleep(1)
    # Check authoritative state before declaring a UI timeout.
    latest = await _read_status(tab)
    if latest["checked"]:
        return
    raise RuntimeError(last_stage)


# ── 主入口 ───────────────────────────────────────────────────────


async def _ensure_page(tab):
    if await _on_cf_challenge(tab):
        try:
            await tab.verify_cf()
        except Exception:
            pass
        if not await _pass_cf_challenge(tab):
            raise RuntimeError("Cloudflare 검증 시간 초과")
    path = urlparse(await tab.evaluate("location.href") or "").path
    if path.startswith(("/login", "/signin")):
        raise ValueError("로그인 세션 만료: _project_hgc_session을 갱신하세요")


async def _verify_identity(tab, user_id: str):
    for _ in range(30):
        await _ensure_page(tab)
        actual = await tab.evaluate(_IDENTITY_JS)
        if actual:
            if actual != user_id:
                raise ValueError("설정된 user_id와 로그인 쿠키의 계정이 다릅니다")
            return
        await tab.sleep(1)
    raise ValueError("로그인된 출석 페이지를 확인할 수 없습니다")


async def _read_account_name(tab, user_id: str) -> str:
    """Read the logged-in header, falling back to this ID's profile heading."""
    if not re.fullmatch(r"[0-9]+", user_id):
        return ""
    try:
        raw = await tab.evaluate("""
        (() => {
            const e = document.querySelector('[data-island="NexusHeader"]');
            if (!e) return null;
            try {
                const user = JSON.parse(e.getAttribute('data-props')).user;
                return user ? JSON.stringify({id: user.id, name: user.name}) : null;
            } catch (_) { return null; }
        })()
        """)
        user = json.loads(raw)
        if isinstance(user, dict) and str(user.get("id")) == user_id and isinstance(user.get("name"), str):
            name = " ".join(user["name"].split())[:100]
            if name:
                logger.info("[%s] 계정명 조회 성공 (로그인 정보)", user_id)
                return name
    except Exception:
        pass
    # Vue may remove the original header props after rendering. The profile's
    # server-rendered h1 is independent of that hydration process.
    script = r"""
    (async () => {
        const path = '/users/' + USER_ID;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 10000);
        try {
            const r = await fetch(path, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
            if (!r.ok || new URL(r.url).pathname.replace(/\/$/, '') !== path) return '';
            const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
            return doc.querySelector('h1.identity-band__name')?.textContent.trim() || '';
        } catch (_) { return ''; }
        finally { clearTimeout(timer); }
    })()
    """.replace("USER_ID", json.dumps(user_id))
    try:
        raw = await tab.evaluate(script, await_promise=True)
        if isinstance(raw, str) and raw.strip():
            logger.info("[%s] 계정명 조회 성공 (프로필 페이지)", user_id)
            return " ".join(raw.split())[:100]
    except Exception:
        pass
    logger.warning("[%s] 계정명 조회 불가: 프로필 응답 또는 표시 구조 확인 필요", user_id)
    return ""


async def _perform_checkin(tab, status: dict) -> CheckinResult:
    if status["checked"]:
        return _result_from_status(status, already_done=True)
    if status.get("cooldown"):
        raise ValueError("출석 쿨다운 상태입니다. 잠시 후 다시 실행하세요")
    bs = None
    for _ in range(30):
        bs = await _get_btn_state(tab)
        if bs and not bs.get("disabled"):
            break
        if bs and bs.get("text") in {"今日已签到", "今天已签到"}:
            latest = await _read_status(tab)
            if latest["checked"]:
                return _result_from_status(latest, already_done=True)
        await tab.sleep(1)
    if bs is None:
        raise ValueError("출석 버튼을 찾지 못했습니다: 새 화면 로딩 상태를 확인하세요")
    if bs.get("disabled") or bs.get("text") == "冷却中":
        raise ValueError("출석 버튼이 대기/쿨다운 상태입니다")
    await _submit_normal(tab)
    latest = await _read_status(tab)
    if not latest["checked"]:
        raise RuntimeError("출석 완료를 확인하지 못했습니다: 인증 창 또는 서버 응답을 확인하세요")
    return _result_from_status(latest)


async def checkin(user_id: str, session_cookie: str) -> CheckinResult:
    """Return daily status and server-reported balance, without conflating failures."""
    if not re.fullmatch(r"[0-9]+", user_id):
        raise ValueError("user_id는 숫자여야 합니다")
    profile = os.path.join(_CHROME_PROFILE, user_id)
    browser = await uc.start(user_data_dir=profile, browser_args=["--disable-gpu", "--disable-software-rasterizer"])
    verified = False
    account_name = ""
    try:
        tab = await browser.get("about:blank")
        await tab.send(uc.cdp.network.delete_cookies(name="_project_hgc_session", domain=".2dfan.com"))
        await tab.send(uc.cdp.network.delete_cookies(name="_project_hgc_session", domain="2dfan.com"))
        await tab.send(uc.cdp.network.set_cookie(
            name="_project_hgc_session", value=session_cookie, domain=".2dfan.com",
            path="/", secure=True, http_only=True,
        ))
        try:
            for attempt in range(2):
                verified = False
                tab = await browser.get(_CHECKIN_URL)
                await tab.sleep(3)
                await asyncio.wait_for(_verify_identity(tab, user_id), timeout=120)
                verified = True
                account_name = await _read_account_name(tab, user_id) or account_name
                status = await _read_status(tab)
                logger.info("[%s] 로그인 계정 일치, 출석 상태=%s, 보유 포인트=%s (시도 %d/2)",
                            user_id, status["checked"], parse_balance(status.get("user_points")), attempt + 1)
                try:
                    result = await asyncio.wait_for(_perform_checkin(tab, status), timeout=150)
                    result.account_name = account_name
                    return result
                except SliderChallengeError:
                    if attempt == 1:
                        raise SliderChallengeError("재시도 후에도 슬라이더 인증으로 전환되었습니다. 수동 인증이 필요합니다") from None
                    logger.info("[%s] 슬라이더 전환: 20초 대기 후 페이지를 새로 열어 한 번 재시도", user_id)
                    await tab.sleep(20)
        except Exception as exc:
            error = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            result = CheckinResult(error=error.replace(session_cookie, "[redacted]"), account_name=account_name)
            # Failure to check in does not prevent reading this account's balance.
            if verified:
                try:
                    latest = await asyncio.wait_for(_read_status(tab), timeout=15)
                    result.points = parse_balance(latest.get("user_points"))
                except Exception:
                    pass
            return result
    finally:
        browser.stop()
