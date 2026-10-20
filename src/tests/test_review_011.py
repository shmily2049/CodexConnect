"""Offline regressions for the 0.10.11 review fixes."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provider_core as core
import switch_profiles as profiles
from profile_store import encode, state_path


class ResponseValidation(unittest.TestCase):
    def test_only_completed_nonblank_text_passes(self):
        settings = core.Settings('fixture', 'Fixture', 'model', 'https://example.com/v1',
                                 auth_mode='token', token='FAKE-KEY')
        good = dict(object='response', status='completed', output=[
            dict(type='message', content=[dict(type='output_text', text='OK FAKE-KEY')])])
        invalid = []
        for status in ('in_progress', 'queued', 'failed', 'incomplete', 'cancelled', None, 'unknown'):
            data = copy.deepcopy(good)
            data['status'] = status
            invalid.append(data)
        for value in ('', ' \n', None, 12, {}, []):
            data = copy.deepcopy(good)
            data['output'][0]['content'][0]['text'] = value
            invalid.append(data)
        for contents in (None, 'OK', {}, 123):
            data = copy.deepcopy(good)
            data['output'][0]['content'] = contents
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), patch('provider_core._request', return_value=json.dumps(data).encode()):
                with self.assertRaises(core.ConfigError):
                    core.test_connection(settings)
        with patch('provider_core._request', return_value=json.dumps(good).encode()):
            result = core.test_connection(settings)
            self.assertIn('OK', result)
            self.assertNotIn('FAKE-KEY', result)


class BackupAndSwitch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.toml'
        self.path.write_text('model="account"\n')
        settings = core.Settings('fixture', 'Fixture', 'model', 'https://example.com/v1',
                                 auth_mode='token', token='FAKE-KEY')
        self.backup = core.apply_plan(core.prepare(core.read_snapshot(self.path), settings))

    def test_malformed_manifest_never_writes_and_does_not_break_labels(self):
        path = self.backup / 'manifest.json'
        valid = json.loads(path.read_bytes())
        before = self.path.read_bytes()
        registry = state_path(self.path).read_bytes()
        for invalid in ([], None, 4, dict(valid, profiles=[]), dict(valid, before_exists='yes')):
            with self.subTest(invalid=invalid):
                path.write_text(json.dumps(invalid))
                self.assertIn('备份损坏', core.backup_description(core.read_snapshot(self.path), self.backup))
                with self.assertRaises(core.ConfigError):
                    core.restore_backup(self.path, self.backup)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(state_path(self.path).read_bytes(), registry)
        path.write_text(json.dumps(valid))
        self.assertIn('可恢复', core.backup_description(core.read_snapshot(self.path), self.backup))

    def test_switch_reads_choices_once_and_rechecks_registry_before_write(self):
        with patch('switch_profiles.choices', wraps=profiles.choices) as reads:
            plan, label = profiles.prepare_switch_review(core.read_snapshot(self.path), 'account')
            self.assertEqual(label, 'ChatGPT套餐')
            self.assertEqual(reads.call_count, 1)
        before = self.path.read_bytes()
        state_path(self.path).write_bytes(encode(set()))
        with self.assertRaises(core.ConfigError):
            core.apply_plan(plan)
        self.assertEqual(self.path.read_bytes(), before)

    def test_registry_change_during_preparation_is_rejected(self):
        original = profiles.choices
        def changed(snap):
            items = original(snap)
            state_path(self.path).write_bytes(encode(set()))
            return items
        with patch('switch_profiles.choices', side_effect=changed), self.assertRaises(core.ConfigError):
            profiles.prepare_switch_review(core.read_snapshot(self.path), 'account')


if __name__ == '__main__':
    unittest.main()
