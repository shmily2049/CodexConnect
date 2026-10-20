import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from dataclasses import replace
from provider_core import *
from switch_profiles import choices, prepare_switch


class SwitchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.toml'
        self.original = '# original comment\nmodel="account-model"\nweb_search="cached"\n[desktop]\nlocale="zh-CN"\n'
        self.path.write_text(self.original, encoding='utf-8')
        self.auth = self.path.parent / 'auth.json'
        self.auth.write_bytes(b'FAKE-ACCOUNT-CACHE-DO-NOT-READ')
        self.s = Settings('gateway', 'My gateway', 'model-a', 'https://example.com/v1',
                          auth_mode='token', token='FAKE-PROFILE-KEY')

    def save(self, s=None):
        return apply_plan(prepare(read_snapshot(self.path), s or self.s))

    def switch(self, key):
        apply_plan(prepare_switch(read_snapshot(self.path), key))

    def test_round_trip_preserves_later_unrelated_edits_and_account_cache(self):
        self.save()
        self.save(replace(self.s, model='model-b'))
        doc = parse_config(self.path.read_bytes())
        doc['mcp_servers'] = {'later': {'url': 'https://example.org/mcp'}}
        self.path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        options = choices(read_snapshot(self.path))
        a = next(p for p in options if p['fields'].get('model') == 'model-a')
        self.switch(a['id'])
        self.assertEqual(parse_config(self.path.read_bytes())['model'], 'model-a')
        self.switch('account')
        doc = parse_config(self.path.read_bytes())
        self.assertEqual(doc['model'], 'account-model')
        self.assertEqual(doc['model_provider'], 'openai')
        self.assertEqual(doc['forced_login_method'], 'chatgpt')
        self.assertEqual(doc['web_search'], 'cached')
        self.assertIn('later', doc['mcp_servers'])
        self.assertIn('# original comment', self.path.read_text())
        self.switch(a['id'])
        doc = parse_config(self.path.read_bytes())
        self.assertNotEqual(doc.get('forced_login_method'), 'api')
        self.assertEqual(doc['model_providers']['gateway']['experimental_bearer_token'], self.s.token)
        self.assertEqual(self.auth.read_bytes(), b'FAKE-ACCOUNT-CACHE-DO-NOT-READ')

    def test_preview_and_options_contain_no_keys_and_no_writes(self):
        self.save()
        raw = self.path.read_bytes()
        plan = prepare_switch(read_snapshot(self.path), 'account')
        self.assertNotIn(self.s.token, plan.preview)
        self.assertNotIn(self.s.token, str(choices(read_snapshot(self.path))))
        self.assertEqual(raw, self.path.read_bytes())

    def test_stale_switch_is_rejected(self):
        self.save()
        plan = prepare_switch(read_snapshot(self.path), 'account')
        self.path.write_bytes(self.path.read_bytes() + b'\n# concurrent\n')
        with self.assertRaises(ConfigError):
            apply_plan(plan)

    def test_old_forced_api_removed_on_save(self):
        self.path.write_text('forced_login_method="api"\n', encoding='utf-8')
        self.save()
        self.assertNotIn('forced_login_method', parse_config(self.path.read_bytes()))

    def test_missing_or_repointed_provider_rejected(self):
        self.save()
        key = next(p['id'] for p in choices(read_snapshot(self.path)) if p['id'] != 'account')
        self.switch('account')
        doc = parse_config(self.path.read_bytes())
        doc['model_providers']['gateway']['base_url'] = 'https://different.example/v1'
        self.path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        with self.assertRaises(ConfigError):
            self.switch(key)
        del doc['model_providers']['gateway']
        self.path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        with self.assertRaises(ConfigError):
            self.switch(key)

    def test_tampered_or_foreign_backup_not_imported(self):
        backup = self.save()
        # Exercise legacy discovery before the registry has been migrated.
        from profile_store import state_path
        state_path(self.path).unlink()
        (backup / 'original.config.toml').write_text('model="tampered"')
        account = choices(read_snapshot(self.path))[0]
        self.assertEqual(account['fields'], {})

    def test_account_defaults_without_original_and_clears_catalog(self):
        self.save()
        from profile_store import state_path
        state_path(self.path).unlink()
        for backup in list_backups(self.path):
            (backup / 'manifest.json').write_text('{}')
        self.switch('account')
        doc = parse_config(self.path.read_bytes())
        self.assertNotIn('model', doc)
        self.assertNotIn('model_catalog_json', doc)
        self.assertEqual(doc['forced_login_method'], 'chatgpt')

    def test_profile_override_and_custom_openai_rejected(self):
        self.save()
        doc = parse_config(self.path.read_bytes())
        doc['profile'] = 'override'
        self.path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        with self.assertRaises(ConfigError):
            self.switch('account')
        del doc['profile']
        doc['model_providers']['openai'] = {'base_url': 'https://different.example'}
        self.path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        with self.assertRaises(ConfigError):
            self.switch('account')

    def test_model_names_survive_switching_on_the_same_service(self):
        self.save(replace(self.s, name='日常编程'))
        self.save(replace(self.s, model='model-b', name='工作专用'))
        options = choices(read_snapshot(self.path))
        a = next(p for p in options if p['fields'].get('model') == 'model-a')
        b = next(p for p in options if p['fields'].get('model') == 'model-b')
        self.assertEqual(a['label'], '日常编程 · model-a')
        self.assertEqual(b['label'], '工作专用 · model-b')
        self.switch(a['id'])
        self.assertEqual(parse_config(self.path.read_bytes())['model_providers']['gateway']['name'], '日常编程')
        self.switch(b['id'])
        doc = parse_config(self.path.read_bytes())
        self.assertEqual(doc['model_providers']['gateway']['name'], '工作专用')
        self.assertEqual(doc['model_providers']['gateway']['experimental_bearer_token'], self.s.token)
        self.save(replace(self.s, model='model-b', name='工作新名称'))
        current = [p for p in choices(read_snapshot(self.path)) if p['fields'].get('model') == 'model-b']
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['label'], '工作新名称 · model-b')

    def test_missing_catalog_rejected(self):
        self.save(replace(self.s, catalog_bytes=b'{"models":[{"slug":"model-a"}]}'))
        key = next(p['id'] for p in choices(read_snapshot(self.path)) if p['id'] != 'account')
        self.switch('account')
        for path in (self.path.parent / 'provider-tool-catalogs').glob('*.json'):
            path.unlink()
        with self.assertRaises(ConfigError):
            self.switch(key)


if __name__ == '__main__':
    unittest.main()
