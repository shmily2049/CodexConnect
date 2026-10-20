import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_core import *


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config.toml'
        self.s = Settings('example', '测试服务', 'example-model', 'https://api.example.com/v1', env_key='EXAMPLE_KEY')

    def tearDown(self):
        self.temp.cleanup()

    def test_preserves_other_settings_and_comments(self):
        raw = b'# keep this comment\nmodel = "old"\n[desktop]\nlocaleOverride = "zh-CN"\n[mcp_servers.demo]\ncommand = "local-tool"\n[model_providers.other]\nname = "Other"\nbase_url = "https://other.example.com"\n'
        self.path.write_bytes(raw)
        plan = prepare(read_snapshot(self.path), self.s)
        obj = parse_config(plan.updated)
        self.assertEqual(obj['model'], 'example-model')
        self.assertNotIn('model', obj['desktop'])
        self.assertEqual(obj['desktop']['localeOverride'], 'zh-CN')
        self.assertEqual(obj['mcp_servers']['demo']['command'], 'local-tool')
        self.assertEqual(obj['model_providers']['other']['name'], 'Other')
        self.assertIn(b'# keep this comment', plan.updated)
        backup = apply_plan(plan)
        self.assertEqual((backup / 'original.config.toml').read_bytes(), raw)
        restore_backup(self.path, backup)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_new_config_restore_removes_only_config(self):
        neighbor = self.path.parent / 'auth.json'
        neighbor.write_text('untouched')
        backup = apply_plan(prepare(read_snapshot(self.path), self.s))
        restore_backup(self.path, backup)
        self.assertFalse(self.path.exists())
        self.assertEqual(neighbor.read_text(), 'untouched')

    def test_backup_order_uses_time_not_random_suffix(self):
        root = self.path.parent / 'provider-tool-backups'
        older = root / '20261019-120000-ffffffff'
        newer = root / '20261019-120000-00000000'
        for index, backup in enumerate((older, newer)):
            backup.mkdir(parents=True)
            manifest = backup / 'manifest.json'
            manifest.write_text('{}')
            timestamp = 1_700_000_000_000_000_000 + index * 1_000_000
            os.utime(manifest, ns=(timestamp, timestamp))
        self.assertEqual(list_backups(self.path), [newer, older])

    def test_concurrent_change_rejected(self):
        self.path.write_text('model="old"\n')
        plan = prepare(read_snapshot(self.path), self.s)
        self.path.write_text('model="new-user-change"\n')
        with self.assertRaises(ConfigError):
            apply_plan(plan)
        self.assertEqual(self.path.read_text(), 'model="new-user-change"\n')

    def test_restore_rejects_new_user_changes(self):
        backup = apply_plan(prepare(read_snapshot(self.path), self.s))
        self.path.write_text('model="manual-edit"\n')
        with self.assertRaises(ConfigError):
            restore_backup(self.path, backup)
        self.assertEqual(self.path.read_text(), 'model="manual-edit"\n')

    def test_invalid_toml_never_overwritten(self):
        self.path.write_text('secret="dummy\n')
        with self.assertRaises(ConfigError) as err:
            read_snapshot(self.path)
        self.assertNotIn('dummy', str(err.exception))
        self.assertEqual(self.path.read_text(), 'secret="dummy\n')

    def test_conflicting_auth_removed_and_preview_redacted(self):
        self.path.write_text('[model_providers.example]\nbase_url="https://api.example.com/v1"\nenv_key="OLD"\nexperimental_bearer_token="old-dummy-secret"\nrequires_openai_auth=true\n')
        settings = replace(self.s, auth_mode='token', token='new-dummy-secret')
        plan = prepare(read_snapshot(self.path), settings)
        pr = parse_config(plan.updated)['model_providers']['example']
        self.assertNotIn('env_key', pr)
        self.assertFalse(pr['requires_openai_auth'])
        self.assertEqual(pr['experimental_bearer_token'], 'new-dummy-secret')
        self.assertNotIn('dummy-secret', plan.preview)

    def test_endpoint_change_requires_new_id(self):
        self.path.write_text('[model_providers.example]\nbase_url="https://old.example.com"\n')
        with self.assertRaises(ConfigError):
            prepare(read_snapshot(self.path), self.s)

    def test_catalog_is_written_only_after_save(self):
        data = b'{"models":[{"slug":"deepseek-flash"}]}'
        settings = replace(self.s, provider='deepseek', model='deepseek-flash', catalog_bytes=data)
        plan = prepare(read_snapshot(self.path), settings)
        self.assertFalse(plan.catalog_target.exists())
        apply_plan(plan)
        self.assertEqual(json.loads(plan.catalog_target.read_bytes())['models'][0]['display_name'], 'deepseek-flash')
        self.assertEqual(parse_config(self.path.read_bytes())['model_catalog_json'], plan.catalog_target.as_posix())

    def test_catalog_must_include_selected_model(self):
        with self.assertRaises(ConfigError):
            prepare(read_snapshot(self.path), replace(self.s, catalog_bytes=b'{"models":[{"slug":"different"}]}'))

    def test_deepseek_requires_catalog(self):
        with self.assertRaises(ConfigError):
            prepare(read_snapshot(self.path), replace(self.s, provider='deepseek'))

    def test_url_validation(self):
        for url in ['http://example.com', 'https://user:pass@example.com', 'https://example.com/?key=dummy',
                    'https://example.com/chat/completions', 'https://example.com/responses']:
            with self.subTest(url=url), self.assertRaises(ConfigError):
                check_url(url)
        self.assertEqual(check_url('http://127.0.0.1:1234/v1/'), 'http://127.0.0.1:1234/v1')

    def test_catalog_html_parser(self):
        parser = CodeBlocks()
        parser.feed('<code><span>{"models":</span><span>[{"slug":"x"}]}</span></code>')
        self.assertEqual(validate_catalog(parser.blocks[0].encode())['models'][0]['slug'], 'x')

    def test_summary_preserves_port_and_masks_url_credentials(self):
        doc = parse_config(b'[model_providers.example]\nbase_url="https://user:password@example.com:8443/v1?key=secret"\n')
        summary = ''.join(safe_summary(doc, 'example'))
        self.assertIn('example.com:8443/v1', summary)
        self.assertNotIn('password', summary)
        self.assertNotIn('secret', summary)

    def test_lock_prevents_parallel_writes(self):
        lock = self.path.parent / '.provider-tool.lock'
        lock.write_text('')
        with self.assertRaises(ConfigError):
            apply_plan(prepare(read_snapshot(self.path), self.s))
        self.assertFalse(self.path.exists())

    def test_tampered_backup_rejected(self):
        self.path.write_text('model="old"')
        backup = apply_plan(prepare(read_snapshot(self.path), self.s))
        (backup / 'original.config.toml').write_text('model="tampered"')
        with self.assertRaises(ConfigError):
            restore_backup(self.path, backup)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.reply = {'object': 'response', 'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]}
        self.status = 200
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                outer.requests.append((self.path, json.loads(raw), self.headers.get('Authorization')))
                self.send_response(outer.status)
                if outer.status == 302:
                    self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/stolen')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(outer.reply).encode())
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.s = Settings('mock', 'Mock', 'test-model', f'http://127.0.0.1:{self.server.server_port}/v1', auth_mode='token', token='not-a-real-key')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_responses_request_and_success(self):
        result = test_connection(self.s)
        self.assertIn('OK', result)
        path, body, auth = self.requests[0]
        self.assertEqual(path, '/v1/responses')
        self.assertEqual(body['model'], 'test-model')
        self.assertEqual(auth, 'Bearer not-a-real-key')
        self.assertNotIn('not-a-real-key', result)

    def test_chat_response_is_not_accepted(self):
        self.reply = {'object': 'chat.completion', 'choices': []}
        with self.assertRaises(ConfigError):
            test_connection(self.s)

    def test_incomplete_response_is_not_success(self):
        self.reply['status'] = 'incomplete'
        with self.assertRaises(ConfigError):
            test_connection(self.s)

    def test_redirect_does_not_forward_secret(self):
        self.status = 302
        with self.assertRaises(ConfigError):
            test_connection(self.s)
        self.assertEqual(len(self.requests), 1)

    def test_http_error_body_not_displayed(self):
        self.status = 401
        self.reply = {'message': 'not-a-real-key echoed'}
        with self.assertRaises(ConfigError) as err:
            test_connection(self.s)
        self.assertNotIn('not-a-real-key', str(err.exception))


if __name__ == '__main__':
    unittest.main()
