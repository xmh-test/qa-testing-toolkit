"""Behavior checks use an isolated local dummy server, never the NAS."""
import hashlib
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http_fault_proxy import State, atomic_json, make_server


class Dummy(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.calls.append((self.path, body))
        if len(self.headers.get_all('Host', [])) != 1:
            self.send_error(400, 'Duplicate Host')
            return
        data = json.dumps({'code': 'TEST_OK', 'data': {'accepted': True}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.calls.append((self.path, b''))
        data = bytes(range(256)) * 1024
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ProxyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.up = ThreadingHTTPServer(('127.0.0.1', 0), Dummy)
        cls.state = State(cls.tmp.name, ('127.0.0.1', cls.up.server_port))
        cls.proxy = make_server('127.0.0.1', 0, cls.state)
        for server in (cls.up, cls.proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.proxy, cls.up):
            server.shutdown()
            server.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        Dummy.calls.clear()
        atomic_json(self.state.rules, {'rules': []})

    def arm(self, mode, **extra):
        import uuid
        rule = dict(id=uuid.uuid4().hex, mode=mode, method='POST', path='/test/create', times=1)
        rule.update(extra)
        atomic_json(self.state.rules, {'rules': [rule]})

    def request(self, method='POST', path='/test/create', host=None, extra_headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.proxy.server_port, timeout=3)
        dest = host or f'127.0.0.1:{self.up.server_port}'
        try:
            headers = {'Authorization': 'secret-test-token', 'Cookie': 'private-test-cookie'}
            headers.update(extra_headers or {})
            conn.request(method, f'http://{dest}{path}', body=b'{"fixture":"only-test"}' if method == 'POST' else None,
                         headers=headers)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_normal_binary_is_byte_exact(self):
        status, body = self.request('GET', '/test/file')
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(body).digest(), hashlib.sha256(bytes(range(256)) * 1024).digest())

    def test_lowercase_host_does_not_create_duplicate_header(self):
        status, _ = self.request(extra_headers={'host': f'127.0.0.1:{self.up.server_port}'})
        self.assertEqual(status, 200)

    def test_abort_before_does_not_contact_upstream_then_recovers(self):
        self.arm('abort_before')
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request()
        self.assertEqual(Dummy.calls, [])
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(len(Dummy.calls), 1)

    def test_drop_response_commits_exactly_one_upstream_call(self):
        self.arm('drop_response', when_code='TEST_OK')
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request()
        self.assertEqual(len(Dummy.calls), 1)
        events = [json.loads(line) for line in self.state.log.read_text().splitlines()]
        self.assertTrue(any(e['event'] == 'response_dropped' and e['upstream_response_complete']
                            and e['upstream_business_code'] == 'TEST_OK' for e in events))

    def test_delay_is_path_limited_and_one_shot(self):
        self.arm('delay_response', delay=.25)
        start = time.monotonic()
        self.request(path='/test/unrelated')
        self.assertLess(time.monotonic() - start, .20)
        start = time.monotonic()
        self.request()
        self.assertGreaterEqual(time.monotonic() - start, .24)
        start = time.monotonic()
        self.request()
        self.assertLess(time.monotonic() - start, .20)

    def test_http_success_business_failure_has_no_upstream_side_effect(self):
        self.arm('mock_json', response={'code': 'TEST_FAIL', 'data': None, 'msg': 'qa-injected-failure'})
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['code'], 'TEST_FAIL')
        self.assertEqual(Dummy.calls, [])

    def test_destination_guard_and_logs_do_not_store_credentials(self):
        self.assertEqual(self.request(host='example.invalid:9999')[0], 403)
        self.assertEqual(Dummy.calls, [])
        self.request()
        logs = self.state.log.read_text()
        self.assertNotIn('secret-test-token', logs)
        self.assertNotIn('private-test-cookie', logs)
        self.assertNotIn('only-test', logs)


    def test_usage_survives_restart(self):
        self.arm('abort_before')
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request()
        restored = State(self.state.folder, self.state.target)
        self.assertIsNone(restored.choose('POST', '/test/create', {}, b''))
        self.assertEqual(self.request()[0], 200)

    def test_query_body_and_method_match_exactly(self):
        self.arm('abort_before', query={'marker': 'test-only'}, body_contains='fixture')
        self.assertEqual(self.request()[0], 200)
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request(path='/test/create?marker=test-only')
        self.assertEqual(len(Dummy.calls), 1)

    def test_clear_restores_normal_forwarding(self):
        self.arm('abort_before')
        atomic_json(self.state.rules, {'rules': []})
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(len(Dummy.calls), 1)

    def test_body_limit_blocks_before_upstream(self):
        original = self.state.max_body_bytes
        self.state.max_body_bytes = 1
        try:
            self.assertEqual(self.request()[0], 413)
            self.assertEqual(Dummy.calls, [])
        finally:
            self.state.max_body_bytes = original

    def test_raw_path_query_and_credentials_not_logged(self):
        self.request(path='/test/secret-path?token=secret-query-value')
        logs = self.state.log.read_text()
        for raw in ('secret-path', 'secret-query-value', 'secret-test-token', 'private-test-cookie', 'only-test'):
            self.assertNotIn(raw, logs)

    def test_non_loopback_bind_rejected(self):
        with self.assertRaises(ValueError):
            make_server('0.0.0.0', 0, self.state)

    def test_connect_is_explicitly_unsupported(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.proxy.server_port, timeout=3)
        try:
            conn.request('CONNECT', 'example.invalid:443')
            response = conn.getresponse()
            self.assertEqual(response.status, 501)
            response.read()
            self.assertEqual(Dummy.calls, [])
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
