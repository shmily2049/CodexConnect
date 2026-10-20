import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_core import read_snapshot
from switch_profiles import choices
import switch_profiles


class ProfileHistoryCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'config.toml'
        self.config.write_text('model="account"\n')
        self.backup = self.config.parent / 'provider-tool-backups/fixture'
        self.backup.mkdir(parents=True)
        self.cache = {}
        self.write_backup('old')

    def write_backup(self, model):
        raw = (f'model="{model}"\nmodel_provider="fixture"\n'
               '[model_providers.fixture]\nname="Fixture"\n'
               'base_url="https://example.com/v1"\nexperimental_bearer_token="FAKE-SECRET"\n').encode()
        (self.backup / 'original.config.toml').write_bytes(raw)
        (self.backup / 'manifest.json').write_text(json.dumps(dict(
            version=1, config_path=str(self.config.resolve()), before_exists=True,
            before_sha256=hashlib.sha256(raw).hexdigest())))

    def read(self):
        return choices(read_snapshot(self.config), history_cache=self.cache)

    def test_cache_reuses_verified_metadata_without_retaining_credentials(self):
        first = self.read()
        with patch('switch_profiles.parse_config', wraps=switch_profiles.parse_config) as parse:
            self.assertEqual(self.read(), first)
            self.assertEqual(parse.call_count, 1)  # Current configuration still parsed freshly.
        self.assertNotIn('FAKE-SECRET', json.dumps(self.cache))
        first[1]['label'] = 'mutated UI item'
        self.assertNotEqual(self.read()[1]['label'], first[1]['label'])

    def test_changed_history_is_reparsed(self):
        self.read()
        self.write_backup('new')
        models = [item['fields'].get('model') for item in self.read()]
        self.assertIn('new', models)
        self.assertNotIn('old', models)

    def test_cached_history_still_requires_hash_and_config_path(self):
        self.read()
        (self.backup / 'original.config.toml').write_bytes(b'model="tampered"\n')
        self.assertEqual(len(self.read()), 1)
        self.write_backup('old')
        meta_path = self.backup / 'manifest.json'
        meta = json.loads(meta_path.read_text())
        meta['config_path'] = str(self.config.parent / 'other/config.toml')
        meta_path.write_text(json.dumps(meta))
        self.assertEqual(len(self.read()), 1)

    def test_removed_history_is_not_resurrected_from_cache(self):
        self.read()
        (self.backup / 'manifest.json').unlink()
        self.assertEqual(len(self.read()), 1)


if __name__ == '__main__':
    unittest.main()
