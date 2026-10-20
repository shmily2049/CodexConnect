from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import unittest
from dataclasses import replace
from provider_presets import PRESETS, get_preset, route_url, identify_preset
from provider_core import Settings, prepare, read_snapshot, parse_config, suggested_provider_id, apply_plan, check_url, ConfigError
from switch_profiles import prepare_switch, choices


class PresetTests(unittest.TestCase):
    def test_all_curated_routes_generate_responses_config(self):
        with tempfile.TemporaryDirectory() as scratch:
            path=Path(scratch)/'config.toml'
            for preset in PRESETS:
                if not preset.docs:
                    continue
                for route in preset.routes:
                    with self.subTest(preset=preset.key,route=route.label):
                        url=route_url(route,'workspace-test')
                        s=Settings(suggested_provider_id(url),preset.service,route.models[0],url,
                                   auth_mode='env',env_key=preset.env,reasoning=preset.reasoning,
                                   catalog_bytes=json.dumps({'models':[{'slug':route.models[0]}]}).encode() if preset.key=='DeepSeek' else None)
                        plan=prepare(read_snapshot(path),s)
                        doc=parse_config(plan.updated)
                        provider=doc['model_providers'][s.provider]
                        self.assertEqual(provider['base_url'],url)
                        self.assertEqual(provider['wire_api'],'responses')
                        self.assertFalse(provider['requires_openai_auth'])
                        self.assertEqual(provider['env_key'],preset.env)
                        self.assertNotEqual(doc.get('forced_login_method'),'api')
            self.assertFalse(path.exists())

    def test_workspace_cannot_change_host_structure(self):
        route=get_preset('通义千问').routes[0]
        for value in ('','a.b','https://abc','abc/other','abc?key=x','$(whoami)','<workspace>','a'*64):
            self.assertEqual(route_url(route,value),'')
        self.assertEqual(route_url(route,'team-123'),'https://team-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1')
        with self.assertRaises(ConfigError):
            check_url(route.url)

    def test_loaded_routes_and_openrouter_models_identified(self):
        for preset in PRESETS:
            if not preset.docs:
                continue
            for route in preset.routes:
                found,found_route,workspace=identify_preset(route_url(route,'team-123'),route.models[0])
                self.assertEqual(found.key,preset.key)
                self.assertEqual(found_route.label,route.label)
                self.assertEqual(workspace,'team-123' if '{workspace}' in route.url else '')
        self.assertEqual(identify_preset('https://unlisted.example/v1','model')[0].key,'自定义 Responses 服务')

    def test_billing_routes_and_ids_are_distinct(self):
        routes=get_preset('豆包 / 火山方舟').routes
        self.assertEqual(len({suggested_provider_id(r.url) for r in routes}),3)
        self.assertTrue(routes[0].url.endswith('/api/v3'))
        self.assertTrue(routes[1].url.endswith('/api/coding/v3'))
        self.assertTrue(routes[2].url.endswith('/api/plan/v3'))

    def test_context_window_switch_and_account_restore(self):
        with tempfile.TemporaryDirectory() as scratch:
            path=Path(scratch)/'config.toml'
            path.write_text('model="original"\nmodel_context_window=128000\n')
            s=Settings('kimi','Kimi','kimi-k3','https://api.moonshot.cn/v1',context_window=1048576)
            apply_plan(prepare(read_snapshot(path),s))
            key=next(p['id'] for p in choices(read_snapshot(path)) if p['id']!='account')
            apply_plan(prepare(read_snapshot(path),replace(s,provider='grok',name='Grok',model='grok-4.6',base_url='https://api.x.ai/v1',context_window=None)))
            self.assertNotIn('model_context_window',parse_config(path.read_bytes()))
            apply_plan(prepare_switch(read_snapshot(path),key))
            self.assertEqual(parse_config(path.read_bytes())['model_context_window'],1048576)
            apply_plan(prepare_switch(read_snapshot(path),'account'))
            self.assertEqual(parse_config(path.read_bytes())['model_context_window'],128000)

    def test_context_window_validation(self):
        with tempfile.TemporaryDirectory() as scratch:
            snap=read_snapshot(Path(scratch)/'config.toml')
            for value in (0,-1,True,100000001,'1024'):
                with self.assertRaises(ConfigError):
                    prepare(snap,Settings('test','Test','model','https://example.com',context_window=value))


if __name__=='__main__':unittest.main()
