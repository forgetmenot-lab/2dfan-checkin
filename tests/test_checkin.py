import io
import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

import api
import main
import notify
from results import CheckinResult, format_result, parse_balance


def status(checked=True, points=101):
    return dict(checked=checked, user_points=points, checkins_count=148, serial_checkins=30)


class ResultTests(unittest.TestCase):
    def test_name_and_numeric_id_display_for_all_statuses(self):
        for result in [CheckinResult(account_name="my_account"),
                       CheckinResult(account_name="my_account", already_done=True),
                       CheckinResult(account_name="my_account", error="인증 실패")]:
            text = "\n".join(main._build_message([(main.Account("123", "cookie"), result)]))
            self.assertIn("`123`", text)
            self.assertIn("my\\_account", text)

    def test_name_fallback_does_not_require_env_changes(self):
        text = "\n".join(main._build_message([(main.Account("123", "cookie"), CheckinResult())]))
        self.assertIn("`123`", text)
        text = "\n".join(main._build_message([(main.Account("123", "cookie", "custom"), CheckinResult())]))
        self.assertIn("custom", text)

    def test_balance_zero_negative_and_missing(self):
        for value, expected in [(0, 0), (101, 101), ("200", 200), (-5, -5),
                                (None, None), (True, None), (1.5, None), ("奖励1积分", None)]:
            with self.subTest(value=value):
                self.assertEqual(parse_balance(value), expected)

    def test_groups_include_balance_for_every_account(self):
        rows = [(main.Account("1", "cookie1"), CheckinResult(points=101)),
                (main.Account("2", "cookie2"), CheckinResult(points=0, already_done=True)),
                (main.Account("3", "cookie3"), CheckinResult(error="쿨다운", points=52)),
                (main.Account("4", "cookie4"), CheckinResult(error="세션 만료"))]
        message = "\n".join(main._build_message(rows))
        for value in ["✅ 성공", "⏭ 이미 완료", "❌ 실패", "101점", "0점", "52점", "조회 불가"]:
            self.assertIn(value, message)
        self.assertNotIn("-1일", message)

    def test_validates_accounts_without_echoing_cookie(self):
        with patch.dict(os.environ, {"ACCOUNTS": '[{"user_id":"../oops","session":"SECRET"}]'}):
            with self.assertRaises(ValueError) as error:
                main.load_accounts()
            self.assertNotIn("SECRET", str(error.exception))


class BrowserFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_name_requires_matching_authenticated_id(self):
        tab = MagicMock(evaluate=AsyncMock(return_value='{"id":123,"name":"my_account"}'))
        self.assertEqual(await api._read_account_name(tab, "123"), "my_account")
        tab.evaluate.side_effect = ['{"id":123,"name":"my_account"}', ""]
        self.assertEqual(await api._read_account_name(tab, "456"), "")
        tab.evaluate.side_effect = None
        tab.evaluate.return_value = None
        self.assertEqual(await api._read_account_name(tab, "123"), "")

    async def test_profile_name_fallback(self):
        tab = MagicMock(evaluate=AsyncMock(side_effect=[None, "example_user"]))
        self.assertEqual(await api._read_account_name(tab, "123456"), "example_user")
        self.assertTrue(tab.evaluate.call_args.kwargs["await_promise"])
        self.assertIn("h1.identity-band__name", tab.evaluate.call_args.args[0])
        self.assertIn('"123456"', tab.evaluate.call_args.args[0])

    async def test_status_awaits_browser_fetch_promise(self):
        tab = MagicMock(evaluate=AsyncMock(return_value=json.dumps(status())))
        self.assertEqual((await api._read_status(tab))["user_points"], 101)
        tab.evaluate.assert_awaited_once_with(api._STATUS_JS, await_promise=True)

    async def test_status_rejects_login_html_and_error_responses(self):
        for response in ["<html>login</html>", '{"http_error":401}', 'null', '{"checked":"false"}']:
            tab = MagicMock(evaluate=AsyncMock(return_value=response))
            with self.assertRaises(RuntimeError):
                await api._read_status(tab)

    async def test_already_checked_returns_balance_without_click(self):
        with patch.object(api, "_submit_normal", new_callable=AsyncMock) as submit:
            result = await api._perform_checkin(MagicMock(), status())
            self.assertTrue(result.already_done)
            self.assertEqual(result.points, 101)
            submit.assert_not_awaited()

    async def test_cooldown_is_not_success(self):
        data = status(False)
        data["cooldown"] = True
        with self.assertRaises(ValueError):
            await api._perform_checkin(MagicMock(), data)

    async def test_disabled_button_is_not_already_checked(self):
        tab = MagicMock(sleep=AsyncMock())
        with patch.object(api, "_get_btn_state", AsyncMock(return_value={"text":"签到", "disabled":True})):
            with self.assertRaises(ValueError):
                await api._perform_checkin(tab, status(False))

    async def test_missing_button_fails_explicitly(self):
        tab = MagicMock(sleep=AsyncMock())
        with patch.object(api, "_get_btn_state", AsyncMock(return_value=None)):
            with self.assertRaisesRegex(ValueError, "버튼"):
                await api._perform_checkin(tab, status(False))

    async def test_success_uses_post_checkin_balance(self):
        with patch.object(api, "_get_btn_state", AsyncMock(return_value={"disabled":False})), \
             patch.object(api, "_submit_normal", AsyncMock()), \
             patch.object(api, "_read_status", AsyncMock(return_value=status(True, 102))):
            result = await api._perform_checkin(MagicMock(), status(False, 101))
            self.assertEqual(result.points, 102)
            self.assertFalse(result.already_done)

    async def test_old_counters_do_not_prove_success(self):
        with patch.object(api, "_get_btn_state", AsyncMock(return_value={"disabled":False})), \
             patch.object(api, "_submit_normal", AsyncMock()), \
             patch.object(api, "_read_status", AsyncMock(return_value=status(False))):
            with self.assertRaises(RuntimeError):
                await api._perform_checkin(MagicMock(), status(False))

    async def test_cookie_account_mismatch_fails_before_click(self):
        tab = MagicMock(evaluate=AsyncMock(return_value="999"))
        with patch.object(api, "_ensure_page", AsyncMock()):
            with self.assertRaisesRegex(ValueError, "계정이 다릅니다"):
                await api._verify_identity(tab, "123")

    async def test_confirmation_is_clicked_once(self):
        button = MagicMock(click=AsyncMock())
        tab = MagicMock(query_selector=AsyncMock(return_value=button),
                        evaluate=AsyncMock(return_value=""), sleep=AsyncMock())
        with patch.object(api, "_get_btn_state", AsyncMock()), \
             patch.object(api, "_check_already_done", AsyncMock(side_effect=[False, False, True])), \
             patch.object(api, "_get_confirm_state", AsyncMock(return_value={"disabled":False})):
            await api._submit_normal(tab)
        self.assertEqual(button.click.await_count, 2)  # daily action + confirmation

    async def test_failure_still_reads_balance_and_stops_browser(self):
        tab = MagicMock(send=AsyncMock(), sleep=AsyncMock())
        browser = MagicMock(get=AsyncMock(return_value=tab))
        with patch.object(api.uc, "start", AsyncMock(return_value=browser)), \
             patch.object(api, "_verify_identity", AsyncMock()), \
             patch.object(api, "_read_status", AsyncMock(return_value=status(False, 99))), \
             patch.object(api, "_perform_checkin", AsyncMock(side_effect=ValueError("쿨다운"))):
            result = await api.checkin("123", "cookie")
        self.assertEqual(result.points, 99)
        self.assertEqual(result.error, "쿨다운")
        browser.stop.assert_called_once()

    async def test_checkbox_waits_for_modal_then_retries(self):
        button = MagicMock(click=AsyncMock())
        tab = MagicMock(query_selector=AsyncMock(return_value=button),
                        evaluate=AsyncMock(return_value=""), sleep=AsyncMock(),
                        verify_cf=AsyncMock(side_effect=[RuntimeError("not ready"), None]))
        with patch.object(api, "_get_btn_state", AsyncMock()), \
             patch.object(api, "_check_already_done", AsyncMock(side_effect=[False]*6+[True])), \
             patch.object(api, "_get_confirm_state", AsyncMock(return_value={"disabled":True})), \
             patch.object(api, "_captcha_state", AsyncMock(return_value={"modal":True})):
            await api._submit_normal(tab)
        self.assertEqual(tab.verify_cf.await_count, 2)
        self.assertEqual(button.click.await_count, 1)

    async def test_slider_timeout_is_explicit_and_does_not_click_checkbox(self):
        button = MagicMock(click=AsyncMock())
        tab = MagicMock(query_selector=AsyncMock(return_value=button),
                        evaluate=AsyncMock(return_value=""), sleep=AsyncMock(), verify_cf=AsyncMock())
        with patch.object(api, "_get_btn_state", AsyncMock()), \
             patch.object(api, "_check_already_done", AsyncMock(return_value=False)), \
             patch.object(api, "_get_confirm_state", AsyncMock(return_value={"disabled":True})), \
             patch.object(api, "_captcha_state", AsyncMock(return_value={"modal":True,"slider":True})), \
             patch.object(api, "_read_status", AsyncMock(return_value=status(False))):
            with self.assertRaisesRegex(RuntimeError, "슬라이더"):
                await api._submit_normal(tab)
        tab.verify_cf.assert_not_awaited()

    async def test_missing_confirmation_is_distinguished_from_auth_failure(self):
        tab = MagicMock(query_selector=AsyncMock(return_value=MagicMock(click=AsyncMock())),
                        evaluate=AsyncMock(return_value=""), sleep=AsyncMock())
        with patch.object(api, "_get_btn_state", AsyncMock()), \
             patch.object(api, "_check_already_done", AsyncMock(return_value=False)), \
             patch.object(api, "_get_confirm_state", AsyncMock(return_value=None)), \
             patch.object(api, "_captcha_state", AsyncMock(return_value={"modal":True})), \
             patch.object(api, "_read_status", AsyncMock(return_value=status(False))):
            with self.assertRaisesRegex(RuntimeError, "확인 버튼을 찾지"):
                await api._submit_normal(tab)

    async def test_one_account_failure_does_not_skip_remaining_accounts(self):
        accounts = [main.Account(str(i), "cookie" + str(i)) for i in range(6)]
        outcomes = [RuntimeError("cookie0"), *[CheckinResult(points=i) for i in range(1, 6)]]
        with patch.object(main, "load_dotenv"), patch.object(main, "load_accounts", return_value=accounts), \
             patch.object(main, "checkin", AsyncMock(side_effect=outcomes)) as check, \
             patch.object(main, "send_discord", return_value=True) as send, \
             patch.dict(os.environ, {"DISCORD_WEBHOOK":"legacy-url"}, clear=True):
            code = await main.main()
        self.assertEqual(code, 1)
        self.assertEqual(check.await_count, 6)
        self.assertEqual(send.call_args.args[0], "legacy-url")
        message = "\n".join(send.call_args.args[1])
        for account in accounts:
            self.assertIn(f"`{account.user_id}`", message)
            self.assertNotIn(account.session, message)


class DiscordTests(unittest.TestCase):
    url = "https://discord.com/api/webhooks/123/test-token"

    def test_long_unicode_messages_are_split_without_loss(self):
        text = "계정😀" * 1800
        chunks = notify.message_chunks([text])
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(x.encode("utf-16-le")) // 2 <= 1900 for x in chunks))

    def test_payload_disables_mentions_and_waits_for_confirmation(self):
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        with patch.object(notify, "urlopen", return_value=response) as open_url:
            self.assertTrue(notify.send_discord(self.url, ["@everyone 계정 101점"]))
        request = open_url.call_args.args[0]
        self.assertIn("wait=true", request.full_url)
        self.assertEqual(json.loads(request.data)["allowed_mentions"], {"parse":[]})

    def test_rate_limit_retries_then_succeeds(self):
        error = HTTPError(self.url, 429, "limit", {}, io.BytesIO(b'{"retry_after":0}'))
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        with patch.object(notify, "urlopen", side_effect=[error, response]) as send, patch.object(notify.time, "sleep"):
            self.assertTrue(notify.send_discord(self.url, ["test"]))
        self.assertEqual(send.call_count, 2)

    def test_network_error_does_not_leak_webhook(self):
        with patch.object(notify, "urlopen", side_effect=URLError(self.url)), self.assertLogs("notify") as logs:
            self.assertFalse(notify.send_discord(self.url, ["test"]))
        self.assertNotIn("test-token", " ".join(logs.output))

    def test_markdown_url_is_rejected(self):
        with patch.object(notify, "urlopen") as send:
            self.assertFalse(notify.send_discord(f"[{self.url}]({self.url})", ["test"]))
        send.assert_not_called()


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, outcomes):
        tab = MagicMock(send=AsyncMock(), sleep=AsyncMock())
        browser = MagicMock(get=AsyncMock(return_value=tab))
        with patch.object(api.uc, "start", AsyncMock(return_value=browser)), \
             patch.object(api, "_verify_identity", AsyncMock()) as identity, \
             patch.object(api, "_read_status", AsyncMock(return_value=status(False, 99))), \
             patch.object(api, "_perform_checkin", AsyncMock(side_effect=outcomes)) as perform:
            result = await api.checkin("123", "cookie")
        browser.stop.assert_called_once()
        return result, tab, identity, perform

    async def test_slider_retries_once_and_returns_latest_balance(self):
        result, tab, identity, perform = await self.run_case([
            api.SliderChallengeError("slider"), CheckinResult(points=100)])
        self.assertEqual(result.points, 100)
        self.assertIsNone(result.error)
        tab.sleep.assert_any_await(20)
        self.assertEqual(identity.await_count, 2)
        self.assertEqual(perform.await_count, 2)

    async def test_repeated_slider_is_bounded_and_keeps_balance(self):
        result, tab, identity, perform = await self.run_case([
            api.SliderChallengeError("slider"), api.SliderChallengeError("slider")])
        self.assertIn("수동 인증", result.error)
        self.assertEqual(result.points, 99)
        self.assertEqual(perform.await_count, 2)

    async def test_other_errors_do_not_retry(self):
        result, tab, identity, perform = await self.run_case([ValueError("쿨다운")])
        self.assertEqual(result.error, "쿨다운")
        self.assertEqual(perform.await_count, 1)


if __name__ == "__main__":
    unittest.main()
