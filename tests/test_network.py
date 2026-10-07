import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import api
import main
from results import CheckinResult


class ProxyTests(unittest.TestCase):
    def test_default_does_not_override_existing_vpn_route(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(any("proxy" in arg for arg in api.browser_options()["browser_args"]))

    def test_supported_proxies_and_remote_socks_dns(self):
        for proxy in ["http://gateway:8080", "https://gateway:8443/", "socks5://gateway:1080", "http://[::1]:8080"]:
            with self.subTest(proxy=proxy), patch.dict(os.environ, {"CHECKIN_PROXY": proxy}, clear=True):
                args = api.browser_options()["browser_args"]
                self.assertIn("--proxy-server=" + proxy.rstrip("/"), args)
                self.assertEqual(any("host-resolver-rules" in arg for arg in args), proxy.startswith("socks5:"))

    def test_invalid_configuration_never_echoes_credentials(self):
        for proxy in ["http://user:SECRET@gateway:8080", "socks5://user:SECRET@gateway:1080",
                      "gateway:8080", "ftp://gateway:21", "http://gateway", "http://gateway:99999",
                      "http://gateway:80/path", "http://gateway:80?SECRET", "http://gateway:80#SECRET",
                      "http://gateway:80;direct://", "http://bad host:80", "http://gateway:bad"]:
            with self.subTest(proxy=proxy), patch.dict(os.environ, {"CHECKIN_PROXY": proxy}, clear=True):
                with self.assertRaises(ValueError) as error:
                    api.browser_options()
                self.assertNotIn("SECRET", str(error.exception))


class NetworkFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_reaches_browser_launch(self):
        tab = MagicMock(send=AsyncMock(), sleep=AsyncMock())
        browser = MagicMock(get=AsyncMock(return_value=tab))
        with patch.dict(os.environ, {"CHECKIN_PROXY": "http://gateway:8080"}, clear=True), \
             patch.object(api.uc, "start", AsyncMock(return_value=browser)) as start, \
             patch.object(api, "_verify_identity", AsyncMock()), \
             patch.object(api, "_read_account_name", AsyncMock(return_value="example")), \
             patch.object(api, "_read_status", AsyncMock(return_value={"checked": True})), \
             patch.object(api, "_perform_checkin", AsyncMock(return_value=CheckinResult(already_done=True))):
            result = await api.checkin("123", "cookie")
        self.assertIsNone(result.error)
        self.assertIn("--proxy-server=http://gateway:8080", start.call_args.kwargs["browser_args"])
        browser.stop.assert_called_once()

    async def test_locked_account_stops_before_any_checkin_or_retry(self):
        tab = MagicMock(send=AsyncMock(), sleep=AsyncMock(),
                        evaluate=AsyncMock(return_value=json.dumps({"locked": True})))
        browser = MagicMock(get=AsyncMock(return_value=tab))
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(api.uc, "start", AsyncMock(return_value=browser)), \
             patch.object(api, "_perform_checkin", AsyncMock()) as perform:
            result = await api.checkin("123", "cookie")
        self.assertIn("계정이 잠겼습니다", result.error)
        perform.assert_not_awaited()
        self.assertEqual(browser.get.await_count, 2)  # blank + one check-in navigation
        browser.stop.assert_called_once()

    async def test_page_diagnostics_distinguish_block_and_connection_error(self):
        for flags, message in [({"blocked": True}, "Cloudflare가 접속을 차단"),
                               ({"network": "ERR_PROXY_CONNECTION_FAILED"}, "ERR_PROXY_CONNECTION_FAILED")]:
            tab = MagicMock(evaluate=AsyncMock(return_value=json.dumps(flags)))
            with self.subTest(flags=flags), self.assertRaisesRegex(RuntimeError, message):
                await api._check_page_failure(tab)

    async def test_valid_page_has_no_false_failure(self):
        for response in [None, "null", "{}", json.dumps({"locked": False, "blocked": False, "network": None})]:
            await api._check_page_failure(MagicMock(evaluate=AsyncMock(return_value=response)))

    async def test_invalid_proxy_fails_before_processing_accounts(self):
        with patch.dict(os.environ, {"CHECKIN_PROXY": "http://user:SECRET@gateway:8080"}, clear=True), \
             patch.object(main, "load_dotenv"), patch.object(main, "checkin", AsyncMock()) as check, \
             self.assertLogs("main") as logs:
            self.assertEqual(await main.main(), 1)
        check.assert_not_awaited()
        self.assertNotIn("SECRET", " ".join(logs.output))
