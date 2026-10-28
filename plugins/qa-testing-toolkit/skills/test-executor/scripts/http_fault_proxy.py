#!/usr/bin/env python3
"""Local HTTP test proxy. Stdlib only. No TLS interception. Forwarded requests may mutate the approved test target."""
import argparse
import hashlib
import http.client
import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HOP = {'connection', 'proxy-connection', 'keep-alive', 'proxy-authenticate',
       'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade'}
MODES = ('pass', 'abort_before', 'drop_response', 'delay_response', 'mock_json')


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


class State:
    def __init__(self, folder, target, timeout=45, max_body_bytes=16 * 1024 * 1024):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.rules = self.folder / 'rules.json'
        self.log = self.folder / 'events.jsonl'
        self.target = target
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes
        self.lock = threading.Lock()
        self.usage = self.folder / 'usage.json'
        self.used = json.loads(self.usage.read_text()) if self.usage.exists() else {}

    def event(self, **data):
        data.update(time=datetime.now(timezone.utc).isoformat(), epoch=time.time())
        with self.lock:
            with os.fdopen(os.open(self.log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), 'a', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False) + '\n')

    def choose(self, method, path, query, body):
        with self.lock:
            try:
                rules = json.loads(self.rules.read_text(encoding='utf-8')).get('rules', [])
            except FileNotFoundError:
                return None
            # Invalid configuration must never silently become an injected fault.
            for rule in rules:
                if rule['mode'] not in MODES or not rule.get('id'):
                    raise ValueError('Invalid rule')
                if rule.get('method') and method != rule['method']:
                    continue
                if path != rule['path']:
                    continue
                if any(query.get(k) != [v] for k, v in rule.get('query', {}).items()):
                    continue
                if rule.get('body_contains', '').encode() not in body:
                    continue
                count = self.used.get(rule['id'], 0)
                if count >= rule.get('times', 1):
                    continue
                self.used[rule['id']] = count + 1
                atomic_json(self.usage, self.used)
                return rule.copy()
        return None


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'QA-Local-Proxy/1'
    sys_version = ''

    def log_message(self, *_):
        # Standard logging would print raw URL/query values.
        pass

    def send_local(self, status, body):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)
        self.close_connection = True

    def disconnect(self):
        self.close_connection = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()

    def do_CONNECT(self):
        self.send_local(501, {'proxy_error': 'HTTPS CONNECT is not supported; no TLS interception'})

    def forward(self):
        state = self.server.qa_state
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        upstream = None
        meta = {'request_id': request_id, 'method': self.command}
        try:
            uri = urlsplit(self.path)
            if uri.scheme:
                if uri.scheme != 'http' or uri.username or uri.password:
                    self.send_local(403, {'proxy_error': 'Only plain HTTP to the approved target is allowed'})
                    return
                host, port = uri.hostname, uri.port or 80
            else:
                authority = urlsplit('http://' + self.headers.get('Host', ''))
                host, port = authority.hostname, authority.port or 80
            if (host, port) != state.target:
                self.send_local(403, {'proxy_error': 'Destination outside the approved target'})
                return
            path = uri.path or '/'
            query = parse_qs(uri.query, keep_blank_values=True)
            # Do not log raw paths, queries, headers or bodies. Correlate by rule/request IDs.
            meta.update(path_sha256=hashlib.sha256(path.encode()).hexdigest())
            if self.headers.get('Transfer-Encoding'):
                self.send_local(501, {'proxy_error': 'Chunked request bodies are not supported'})
                return
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > state.max_body_bytes:
                self.send_local(413, {'proxy_error': 'Request body exceeds proxy management-test limit'})
                return
            body = self.rfile.read(length) if length else b''
            if len(body) != length:
                raise ValueError('Incomplete incoming request body')
            meta.update(request_bytes=length, request_sha256=hashlib.sha256(body).hexdigest())
            rule = state.choose(self.command, path, query, body)
            mode = rule['mode'] if rule else 'pass'
            meta.update(mode=mode, rule_id=rule['id'] if rule else None)
            state.event(event='received', **meta)
            if mode == 'abort_before':
                state.event(event='aborted_before_upstream', upstream_opened=False, **meta)
                self.disconnect()
                return
            if mode == 'mock_json':
                self.send_local(rule.get('http_status', 200), rule['response'])
                state.event(event='mock_sent', upstream_opened=False,
                            injected_business_code=rule['response'].get('code'), **meta)
                return
            # Do not retain or log auth headers, cookies, or payload contents.
            hop = HOP | {v.strip().lower() for v in self.headers.get('Connection', '').split(',')}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in hop | {'host'}}
            headers['Host'] = f'{host}:{port}'
            headers['Connection'] = 'close'
            upstream = http.client.HTTPConnection(host, port, timeout=state.timeout)
            target_path = path + ('?' + uri.query if uri.query else '')
            upstream.request(self.command, target_path, body=body if length else None, headers=headers)
            response = upstream.getresponse()
            response_headers = response.getheaders()
            content_type = response.getheader('Content-Type', '')
            json_response = 'json' in content_type.lower()
            # Management JSON is bounded; ordinary binary responses stream without buffering.
            if json_response:
                data = response.read(state.max_body_bytes + 1)
                if len(data) > state.max_body_bytes:
                    raise ValueError('JSON response exceeds proxy inspection limit')
            else:
                data = None
            business_code = None
            if data is not None:
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        business_code = parsed.get('code')
                except (ValueError, UnicodeDecodeError):
                    pass
            meta.update(upstream_http=response.status, upstream_business_code=business_code)
            state.event(event='upstream_response', **meta)
            condition_met = not rule or not rule.get('when_code') or business_code == rule['when_code']
            if mode == 'drop_response' and condition_met:
                size = len(data) if data is not None else 0
                if data is None:
                    while True:
                        block = response.read(65536)
                        if not block:
                            break
                        size += len(block)
                state.event(event='response_dropped', response_bytes=size,
                            upstream_response_complete=True, **meta)
                self.disconnect()
                return
            if mode == 'delay_response' and condition_met:
                delay = min(max(float(rule.get('delay', 5)), 0), 60)
                state.event(event='delaying_response', delay_seconds=delay, **meta)
                time.sleep(delay)
            response_hop = HOP | {v.strip().lower() for v in response.getheader('Connection', '').split(',')}
            self.send_response(response.status, response.reason)
            for k, v in response_headers:
                if k.lower() not in response_hop and (data is None or k.lower() != 'content-length'):
                    self.send_header(k, v)
            if data is not None:
                self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            size = 0
            if self.command != 'HEAD':
                if data is not None:
                    self.wfile.write(data)
                    size = len(data)
                else:
                    while True:
                        block = response.read(65536)
                        if not block:
                            break
                        self.wfile.write(block)
                        size += len(block)
            self.close_connection = True
            state.event(event='forwarded', response_bytes=size,
                        elapsed_seconds=round(time.monotonic() - started, 6), **meta)
        except Exception as exc:
            state.event(event='proxy_error', error_type=type(exc).__name__, **meta)
            self.close_connection = True
            # Errors belong to the local proxy, not automatically to the product.
            try:
                self.send_local(502, {'proxy_error': type(exc).__name__, 'request_id': request_id})
            except (OSError, ValueError):
                pass
        finally:
            if upstream:
                upstream.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = forward


def make_server(bind, port, state):
    if bind != '127.0.0.1':
        raise ValueError('This test proxy only binds to 127.0.0.1')
    server = ThreadingHTTPServer((bind, port), Proxy)
    server.daemon_threads = True
    server.qa_state = state
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True, help='Per-run state directory; rules may contain sensitive match values')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, required=True)
    serve.add_argument('--timeout', type=float, default=45)
    serve.add_argument('--max-body-bytes', type=int, default=16 * 1024 * 1024)
    serve.add_argument('--target-host', required=True)
    serve.add_argument('--target-port', type=int, required=True)
    arm = sub.add_parser('arm')
    arm.add_argument('--mode', choices=MODES[1:], required=True)
    arm.add_argument('--path', required=True, help='Exact observed request path; no guessed endpoints')
    arm.add_argument('--method', choices=('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'), required=True)
    arm.add_argument('--times', type=int, default=1)
    arm.add_argument('--delay', type=float, default=5)
    arm.add_argument('--when-code')
    arm.add_argument('--body-contains', default='')
    arm.add_argument('--query-file', type=Path, help='JSON object of exact query key/string value matches')
    arm.add_argument('--response-file', type=Path)
    arm.add_argument('--http-status', type=int, default=200)
    sub.add_parser('clear')
    sub.add_parser('status')
    args = parser.parse_args()
    rulefile = args.state_dir / 'rules.json'
    if args.command == 'serve':
        if not (0 < args.port < 65536 and 0 < args.target_port < 65536 and args.timeout > 0 and args.max_body_bytes > 0):
            parser.error('Ports must be 1..65535; timeout and body limit must be positive')
        state = State(args.state_dir, (args.target_host.lower(), args.target_port), args.timeout, args.max_body_bytes)
        server = make_server('127.0.0.1', args.port, state)
        print(json.dumps({'listen': f'127.0.0.1:{server.server_port}',
                          'allowed_destination': f'{args.target_host}:{args.target_port}',
                          'rules': str(rulefile), 'event_log': str(state.log)}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == 'arm':
        if not args.path.startswith('/') or '?' in args.path or args.times < 1 or not 0 <= args.delay <= 60:
            parser.error('Use exact path without query and times >= 1')
        rule = dict(id=uuid.uuid4().hex, mode=args.mode, path=args.path,
                    method=args.method, times=args.times, delay=args.delay,
                    body_contains=args.body_contains, when_code=args.when_code)
        if args.query_file:
            rule['query'] = json.loads(args.query_file.read_text(encoding='utf-8'))
            if not isinstance(rule['query'], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rule['query'].items()):
                parser.error('query-file must contain a JSON object of string values')
        if args.mode == 'mock_json':
            if not args.response_file:
                parser.error('mock_json requires --response-file')
            rule['response'] = json.loads(args.response_file.read_text(encoding='utf-8'))
            if not isinstance(rule['response'], dict):
                parser.error('Mock response must be a JSON object')
            rule['http_status'] = args.http_status
        atomic_json(rulefile, {'rules': [rule]})
        print(json.dumps({'armed_rule_id': rule['id'], 'mode': rule['mode'],
                          'method': rule['method'], 'times': rule['times']}))
    elif args.command == 'clear':
        atomic_json(rulefile, {'rules': []})
        print('All injection rules cleared; normal forwarding continues.')
    else:
        rules = json.loads(rulefile.read_text(encoding='utf-8')).get('rules', []) if rulefile.exists() else []
        print(json.dumps({'rules': [{k: r[k] for k in ('id', 'mode', 'method', 'times') if k in r} for r in rules]}))


if __name__ == '__main__':
    main()
