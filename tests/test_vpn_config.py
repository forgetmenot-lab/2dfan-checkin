import unittest

from vpn.prepare_config import convert


class VpnConfigTests(unittest.TestCase):
    def test_embedded_keys_preserved_and_remote_resolved(self):
        source = 'client\r\nremote vpn.example 15021 udp\r\nroute-method exe\r\n<key>\r\nprivate-key-fixture\r\n</key>\r\n'
        hosts = []
        def resolve(host):
            hosts.append(host)
            return '192.0.2.10'
        result = convert(source, resolve)
        self.assertEqual(hosts, ['vpn.example'])
        self.assertIn('remote 192.0.2.10 15021 udp\n', result)
        self.assertIn('<key>\nprivate-key-fixture\n</key>', result)
        self.assertNotIn('route-method', result)

    def test_rejects_external_hooks_and_files(self):
        for directive in ('up hook.sh', 'plugin module.so', 'config other.ovpn', 'ca relative.crt'):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                convert('remote vpn.example 1194\n' + directive, lambda _: '192.0.2.10')

    def test_rejects_incomplete_or_ambiguous_profile(self):
        for source in ('client', 'remote vpn.example 1194\n<key>\nincomplete',
                       'remote a 1194\nremote b 1194'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                convert(source, lambda _: '192.0.2.10')

    def test_resolution_failure_stops_preparation(self):
        def failure(_):
            raise OSError('DNS unavailable')
        with self.assertRaises(OSError):
            convert('remote vpn.example 1194', failure)
