import errno
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, MagicMock, patch

import diagnose


class ProbeCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def run_probe(self, blocked=False, navigation_error=None):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'ip=192.0.2.1\nloc=US\n'
        tab = MagicMock(evaluate=AsyncMock(return_value=json.dumps({
            'title': '2DFan', 'host': '2dfan.com', 'challenge': False,
            'blocked': blocked, 'network': False, 'content': True})))
        process = MagicMock(wait=AsyncMock(return_value=0))
        browser = MagicMock(get=AsyncMock(return_value=tab), _process=process)
        if navigation_error:
            browser.get.side_effect = navigation_error
        profile = MagicMock(name='profile')
        profile.name = '/tmp/public-probe-fixture'
        profile.cleanup.side_effect = OSError(errno.ENOTEMPTY, 'Directory not empty')
        output = io.StringIO()
        with patch.object(diagnose.urllib.request, 'urlopen', return_value=response), \
             patch.object(diagnose.uc, 'start', AsyncMock(return_value=browser)), \
             patch.object(diagnose.tempfile, 'TemporaryDirectory', return_value=profile), \
             patch.object(diagnose.asyncio, 'sleep', AsyncMock()), redirect_stdout(output):
            result = await diagnose.probe()
        browser.stop.assert_called_once()
        process.wait.assert_awaited_once()
        self.assertIn('temporary_profile', output.getvalue())
        return result

    async def test_cleanup_failure_does_not_turn_success_into_connection_error(self):
        self.assertEqual(await self.run_probe(), 0)

    async def test_cleanup_failure_does_not_hide_blocked_page(self):
        self.assertEqual(await self.run_probe(blocked=True), 2)

    async def test_cleanup_failure_preserves_navigation_error(self):
        with self.assertRaisesRegex(RuntimeError, 'navigation failed'):
            await self.run_probe(navigation_error=RuntimeError('navigation failed'))
