"""State transitions and rollback failures using isolated synthetic configuration."""
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provider_core as core
from provider_core import Settings, ConfigError, prepare, apply_plan, read_snapshot, restore_backup, parse_config, list_backups
from switch_profiles import choices, prepare_switch
from profile_store import decorate_plan, read_state, state_path, delete_choice, parse_state


class AuditFixes(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'config.toml'
        self.path.write_text('model="account-model"\n# preserve\n')
        self.settings = Settings('fixture', 'First', 'a', 'https://example.com/v1', auth_mode='token', token='FAKE-AUDIT-KEY')

    def save(self, model='a'):
        return apply_plan(prepare(read_snapshot(self.path), replace(self.settings, model=model)))

    def choice(self, model):
        return next(i for i in choices(read_snapshot(self.path)) if i['fields'].get('model') == model)

    def edit(self):
        self.save()
        before = read_state(self.path)[0]
        old = self.choice('a')
        backup = apply_plan(decorate_plan(prepare(read_snapshot(self.path), replace(self.settings, model='b')), old['id']))
        return backup, before, old

    def test_restored_model_remains_available_after_leaving_it(self):
        backup, before, old = self.edit()
        safety = restore_backup(self.path, backup)
        self.assertEqual(read_state(self.path)[0], before)
        apply_plan(prepare_switch(read_snapshot(self.path), 'account'))
        self.assertEqual(self.choice('a')['id'], old['id'])
        self.assertTrue((safety / 'original.profiles.json').is_file())

    def test_restore_can_itself_be_undone(self):
        backup, _, _ = self.edit()
        edited = self.path.read_bytes(), read_state(self.path)[0]
        safety = restore_backup(self.path, backup)
        restore_backup(self.path, safety)
        self.assertEqual((self.path.read_bytes(), read_state(self.path)[0]), edited)

    def test_restore_rejects_later_profile_delete_even_when_config_unchanged(self):
        self.save()
        backup = self.save('b')
        delete_choice(read_snapshot(self.path), self.choice('a')['id'])
        before = self.path.read_bytes(), read_state(self.path)[0]
        with self.assertRaises(ConfigError):
            restore_backup(self.path, backup)
        self.assertEqual((self.path.read_bytes(), read_state(self.path)[0]), before)

    def test_restore_failed_config_write_rolls_back_state(self):
        backup, _, _ = self.edit()
        before = self.path.read_bytes(), read_state(self.path)[0]
        original = core._atomic_write
        def fail(path, data):
            if path == self.path:
                raise OSError('synthetic failure')
            original(path, data)
        with patch('provider_core._atomic_write', side_effect=fail), self.assertRaises(OSError):
            restore_backup(self.path, backup)
        self.assertEqual((self.path.read_bytes(), read_state(self.path)[0]), before)

    def test_tampered_profile_backup_rejected(self):
        backup, _, _ = self.edit()
        (backup / 'original.profiles.json').write_bytes(b'{}')
        before = self.path.read_bytes(), read_state(self.path)[0]
        with self.assertRaises(ConfigError):
            restore_backup(self.path, backup)
        self.assertEqual((self.path.read_bytes(), read_state(self.path)[0]), before)

    def test_legacy_restore_preserves_other_deletions_and_unhides_restored_model(self):
        self.save('other')
        self.save('a')
        a = self.choice('a')
        other = self.choice('other')
        backup = apply_plan(decorate_plan(prepare(read_snapshot(self.path), replace(self.settings, model='b')), a['id']))
        meta_path = backup / 'manifest.json'
        meta = json.loads(meta_path.read_bytes())
        meta.pop('profiles')
        meta_path.write_text(json.dumps(meta))
        delete_choice(read_snapshot(self.path), other['id'])
        restore_backup(self.path, backup)
        apply_plan(prepare_switch(read_snapshot(self.path), 'account'))
        ids = [i['id'] for i in choices(read_snapshot(self.path))]
        self.assertIn(a['id'], ids)
        self.assertNotIn(other['id'], ids)

    def test_registry_survives_missing_backups_without_reading_them(self):
        self.save()
        self.save('b')
        with patch('switch_profiles.list_backups', side_effect=AssertionError('must not scan history')):
            self.assertEqual(self.choice('a')['fields']['model'], 'a')
            apply_plan(prepare_switch(read_snapshot(self.path), 'account'))
            self.assertEqual(self.choice('a')['fields']['model'], 'a')
        self.assertNotIn(b'FAKE-AUDIT-KEY', read_state(self.path)[0])
        self.assertEqual(parse_state(read_state(self.path)[0])['version'], 2)

    def test_state_cannot_smuggle_credentials_in_fields(self):
        self.save()
        data = json.loads(read_state(self.path)[0])
        data['choices'][0]['fields']['experimental_bearer_token'] = 'FAKE'
        with self.assertRaises(ConfigError):
            parse_state(json.dumps(data).encode())

    def test_account_url_reset_requires_explicit_option_and_is_reversible(self):
        self.path.write_text('model="account-model"\nopenai_base_url="https://proxy.example/v1"\n# preserve\n')
        self.save()
        snap = read_snapshot(self.path)
        with self.assertRaises(ConfigError):
            prepare_switch(snap, 'account')
        backup = apply_plan(prepare_switch(snap, 'account', reset_account_url=True))
        self.assertNotIn('openai_base_url', parse_config(self.path.read_bytes()))
        self.assertIn(b'# preserve', self.path.read_bytes())
        restore_backup(self.path, backup)
        self.assertEqual(self.path.read_bytes(), snap.raw)

    def test_legacy_profile_is_rejected_by_save_and_switch(self):
        for raw in ('profile="work"\n', '[profiles.work]\nmodel="old"\n'):
            self.path.write_text(raw)
            snap = read_snapshot(self.path)
            with self.assertRaisesRegex(ConfigError, '旧式 profile'):
                prepare(snap, self.settings)
            with self.assertRaisesRegex(ConfigError, '旧式 profile'):
                prepare_switch(snap, 'account')
            self.assertEqual(self.path.read_bytes(), snap.raw)

    def test_backup_label_marks_model_changes_and_conflicts(self):
        backup = self.save()
        label = core.backup_description(read_snapshot(self.path), backup)
        self.assertIn('可恢复', label)
        self.assertIn('account-model → a', label)
        self.assertNotIn('FAKE', label)
        self.path.write_text('model="later"\n')
        self.assertIn('有后续改动', core.backup_description(read_snapshot(self.path), backup))


if __name__ == '__main__':
    unittest.main()
