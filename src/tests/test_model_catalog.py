"""Name sync regression tests; no real config, credentials, network or desktop."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_catalog import display_catalog, templates
from provider_core import Settings, prepare, read_snapshot, apply_plan, parse_config, restore_backup, ConfigError
from switch_profiles import choices, prepare_switch

class ModelNameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.toml'
        self.s = Settings('fixture', '我的网关', 'DeepSeek-v4-flash', 'http://127.0.0.1:1', token='FAKE', auth_mode='token')

    def test_no_write_until_confirmation_and_restores_original(self):
        original = b'# retain\nmodel_provider="openai"\nmodel="gpt-6-astra"\n'
        self.path.write_bytes(original)
        plan = prepare(read_snapshot(self.path), self.s)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(plan.catalog_target.exists())
        item = json.loads(plan.catalog_bytes)['models'][0]
        self.assertEqual(item['slug'], self.s.model)
        self.assertEqual(item['display_name'], self.s.model)
        self.assertEqual(item['visibility'], 'list')
        self.assertEqual(item['supported_reasoning_levels'], [])
        self.assertNotIn('FAKE', plan.catalog_bytes.decode())
        backup = apply_plan(plan)
        self.assertEqual(plan.catalog_target.read_bytes(), plan.catalog_bytes)
        restore_backup(self.path, backup)
        self.assertEqual(self.path.read_bytes(), original)

    def test_import_preserves_capabilities_prompt_and_original_file(self):
        entry = {'slug': self.s.model, 'display_name': 'old', 'visibility': 'hide',
                 'context_window': 999999, 'model_messages': {'instructions_template': 'Provider prompt'},
                 'input_modalities': ['text'], 'supported_reasoning_levels': [{'effort':'high','description':'provider'}],
                 'custom_future_field': {'keep': True}}
        imported = {'models':[entry], 'custom_top':'keep'}
        original = copy.deepcopy(imported)
        source = self.path.parent / 'provider.json'
        source.write_text(json.dumps(imported),encoding='utf-8')
        before = source.read_bytes()
        plan = prepare(read_snapshot(self.path),replace(self.s,catalog_path=str(source)))
        result=json.loads(plan.catalog_bytes); actual=result['models'][0]
        for key in ('context_window','model_messages','input_modalities','supported_reasoning_levels','custom_future_field'):
            self.assertEqual(actual[key],entry[key])
        self.assertNotIn('max_context_window',actual)
        self.assertNotIn('base_instructions',actual)
        self.assertEqual(result['custom_top'],'keep')
        apply_plan(plan)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(imported,original)

    def test_builtin_metadata_not_replaced_with_generic_defaults(self):
        _, known=templates()
        expected=copy.deepcopy(known['gpt-6-astra'])
        actual=json.loads(display_catalog('gpt-6-astra'))['models'][0]
        expected.update(display_name='gpt-6-astra',visibility='list')
        self.assertEqual(actual,expected)

    def test_switch_account_restores_catalog_and_custom_switch_restores_name(self):
        self.path.write_text('model_provider="openai"\nmodel="gpt-6-astra"\n',encoding='utf-8')
        apply_plan(prepare(read_snapshot(self.path),self.s))
        apply_plan(prepare_switch(read_snapshot(self.path),'account'))
        account=parse_config(self.path.read_bytes())
        self.assertNotIn('model_catalog_json',account)
        self.assertEqual(account['forced_login_method'],'chatgpt')
        choice=next(i for i in choices(read_snapshot(self.path)) if i['id']!='account')
        plan=prepare_switch(read_snapshot(self.path),choice['id'])
        apply_plan(plan)
        self.assertEqual(json.loads(plan.catalog_target.read_bytes())['models'][0]['display_name'],self.s.model)

    def test_legacy_scheme_without_catalog_is_upgraded_on_switch(self):
        self.path.write_text('model="legacy-id"\nmodel_provider="legacy"\n[model_providers.legacy]\nname="Legacy"\nbase_url="http://127.0.0.1:1"\nwire_api="responses"\nrequires_openai_auth=false\nexperimental_bearer_token="FAKE"\n',encoding='utf-8')
        choice=next(i for i in choices(read_snapshot(self.path)) if i['id']!='account')
        plan=prepare_switch(read_snapshot(self.path),choice['id'])
        self.assertFalse(plan.catalog_target.exists())
        apply_plan(plan)
        self.assertEqual(json.loads(plan.catalog_target.read_bytes())['models'][0]['display_name'],'legacy-id')

    def test_model_id_case_is_preserved(self):
        for model in ('deepseek-v4-flash','DeepSeek-v4-flash','org/model-v1'):
            entry=json.loads(display_catalog(model))['models'][0]
            self.assertEqual((entry['slug'],entry['display_name']),(model,model))

    def test_catalog_collision_is_rejected(self):
        plan=prepare(read_snapshot(self.path),self.s)
        plan.catalog_target.parent.mkdir()
        plan.catalog_target.write_bytes(b'changed')
        with self.assertRaises(ConfigError): apply_plan(plan)
        self.assertFalse(self.path.exists())

if __name__ == '__main__': unittest.main()
