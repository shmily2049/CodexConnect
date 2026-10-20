import re
import unittest
from pathlib import Path
from dataclasses import replace
from provider_core import Snapshot, Settings, ConfigError, suggested_provider_id, resolve_provider_id, prepare, parse_config


class ProviderIdTests(unittest.TestCase):
    def snapshot(self, raw=''):
        return Snapshot(Path('config.toml'),bool(raw),raw.encode())

    def test_stable_id_and_safe_characters(self):
        for url in ['https://api.example.com/v1', 'http://127.0.0.1:1234', 'http://[::1]:1234/v1', 'https://例子.测试/v1']:
            pid=suggested_provider_id(url)
            self.assertRegex(pid,r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
            self.assertEqual(pid,suggested_provider_id(url+'/'))
        self.assertEqual(suggested_provider_id('https://api.deepseek.com'),'deepseek')

    def test_different_paths_ports_and_hosts_have_different_ids(self):
        urls=['https://api.example.com/v1','https://api.example.com/v2','https://api.example.com:8443/v1','https://other.example.com/v1']
        self.assertEqual(len({suggested_provider_id(url) for url in urls}),4)

    def test_collision_keeps_existing_provider_and_headers(self):
        url='https://api.example.com/v1'
        pid=suggested_provider_id(url)
        snap=self.snapshot(f'[model_providers.{pid}]\nbase_url="https://other.example.com"\n[model_providers.{pid}.http_headers]\nX-Custom="keep"\n')
        chosen=resolve_provider_id(snap,url)
        self.assertNotEqual(pid,chosen)
        plan=prepare(snap,Settings(chosen,'新服务','model',url,env_key='EXAMPLE_KEY'))
        providers=parse_config(plan.updated)['model_providers']
        self.assertEqual(providers[pid]['base_url'],'https://other.example.com')
        self.assertEqual(providers[pid]['http_headers']['X-Custom'],'keep')
        self.assertNotIn('http_headers',providers[chosen])
        self.assertEqual(resolve_provider_id(self.snapshot(plan.updated.decode()),url),chosen)

    def test_loaded_id_preserved_only_for_same_address(self):
        snap=self.snapshot('[model_providers.my_team]\nbase_url="https://api.example.com/v1"\n')
        self.assertEqual(resolve_provider_id(snap,'https://api.example.com/v1/','my_team'),'my_team')
        self.assertNotEqual(resolve_provider_id(snap,'https://new.example.com','my_team'),'my_team')

    def test_unknown_and_builtin_ids_not_reused(self):
        snap=self.snapshot('[model_providers.openai]\nbase_url="https://api.example.com"\n')
        self.assertNotEqual(resolve_provider_id(snap,'https://api.example.com','openai'),'openai')
        self.assertNotEqual(resolve_provider_id(snap,'https://api.example.com','missing'),'missing')

    def test_multiple_collisions_and_missing_address(self):
        pid=suggested_provider_id('https://api.example.com')
        snap=self.snapshot(f'[model_providers.{pid}]\nname="unknown"\n[model_providers.{pid}_1]\nbase_url="https://elsewhere.example.com"\n')
        self.assertEqual(resolve_provider_id(snap,'https://api.example.com'),pid+'_2')

    def test_deepseek_collision_still_requires_catalog(self):
        snap=self.snapshot('[model_providers.deepseek]\nbase_url="https://elsewhere.example.com"\n')
        pid=resolve_provider_id(snap,'https://api.deepseek.com')
        self.assertEqual(pid,'deepseek_1')
        with self.assertRaisesRegex(ConfigError,'模型目录'):
            prepare(snap,Settings(pid,'DeepSeek','deepseek-flash','https://api.deepseek.com'))

    def test_invalid_url_does_not_generate_an_id(self):
        with self.assertRaises(ConfigError):suggested_provider_id('')
        with self.assertRaises(ConfigError):suggested_provider_id('https://user:secret@example.com')
