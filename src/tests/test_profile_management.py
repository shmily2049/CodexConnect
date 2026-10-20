import sys,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from provider_core import *
from switch_profiles import choices,prepare_switch
from profile_store import delete_choice,decorate_plan,read_state,state_path,resolve_choices

class ProfileManagementTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'config.toml';self.path.write_text('model="account-model"\n')
        self.s=Settings('fixture','First','a','https://example.com/v1',auth_mode='token',token='FAKE-KEY')
        apply_plan(prepare(read_snapshot(self.path),self.s))
        apply_plan(prepare(read_snapshot(self.path),replace(self.s,model='b',name='Second')))
    def item(self,model):return next(x for x in choices(read_snapshot(self.path)) if x['fields'].get('model')==model)
    def test_delete_persists_without_touching_config_or_credentials(self):
        before=self.path.read_bytes();backups=list_backups(self.path);item=self.item('a')
        delete_choice(read_snapshot(self.path),item['id'])
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(list_backups(self.path),backups)
        self.assertFalse(any(x['id']==item['id'] for x in choices(read_snapshot(self.path))))
        self.assertNotIn(b'FAKE-KEY',state_path(self.path).read_bytes())
        apply_plan(prepare_switch(read_snapshot(self.path),'account'))
        self.assertFalse(any(x['id']==item['id'] for x in choices(read_snapshot(self.path))))
    def test_active_and_account_protected(self):
        for key in ('account',self.item('b')['id']):
            with self.assertRaises(ConfigError):delete_choice(read_snapshot(self.path),key)
    def test_edit_replaces_original_and_readd_deleted_is_allowed(self):
        a=self.item('a');plan=prepare(read_snapshot(self.path),replace(self.s,model='edited'))
        apply_plan(decorate_plan(plan,a['id']))
        self.assertFalse(any(x['id']==a['id'] for x in choices(read_snapshot(self.path))))
        self.assertTrue(self.item('edited')['current'])
        apply_plan(prepare(read_snapshot(self.path),self.s))
        apply_plan(prepare_switch(read_snapshot(self.path),'account'))
        self.assertEqual(self.item('a')['id'],a['id'])
    def test_concurrent_delete_invalidates_prepared_save(self):
        plan=prepare(read_snapshot(self.path),replace(self.s,model='c'));before=self.path.read_bytes()
        delete_choice(read_snapshot(self.path),self.item('a')['id'])
        with self.assertRaises(ConfigError):apply_plan(plan)
        self.assertEqual(self.path.read_bytes(),before)
    def test_resolved_view_rejects_delete_before_preview(self):
        snap=read_snapshot(self.path);resolved=resolve_choices(snap);item=self.item('a')
        delete_choice(snap,item['id'])
        with self.assertRaises(ConfigError):
            prepare(snap,replace(self.s,model='edited'),retired=item['id'],resolved=resolved)
        self.assertFalse(any(x['id']==item['id'] for x in choices(snap)))
    def test_resolved_delete_checks_registry_and_config(self):
        snap=read_snapshot(self.path);resolved=resolve_choices(snap);item=self.item('a')
        delete_choice(snap,item['id'])
        with self.assertRaises(ConfigError):delete_choice(snap,item['id'],resolved=resolved)
        fresh=resolve_choices(snap)
        self.path.write_bytes(snap.raw+b'\n# external change\n')
        with self.assertRaises(ConfigError):delete_choice(snap,item['id'],resolved=fresh)
    def test_resolved_edit_does_not_scan_history_again(self):
        snap=read_snapshot(self.path);resolved=resolve_choices(snap);item=self.item('a')
        with patch('switch_profiles.choices',side_effect=AssertionError('duplicate scan')):
            plan=prepare(snap,replace(self.s,model='edited'),retired=item['id'],resolved=resolved)
            apply_plan(plan)
        self.assertFalse(any(x['id']==item['id'] for x in choices(read_snapshot(self.path))))
    def test_failed_config_write_rolls_back_profile_state(self):
        import provider_core
        before=self.path.read_bytes();state=read_state(self.path)[0]
        plan=decorate_plan(prepare(read_snapshot(self.path),replace(self.s,model='c')),self.item('a')['id'])
        original=provider_core._atomic_write
        def fail(path,data):
            if path==self.path:raise OSError('fixture write failure')
            original(path,data)
        with patch('provider_core._atomic_write',side_effect=fail):
            with self.assertRaises(OSError):apply_plan(plan)
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(read_state(self.path)[0],state)
    def test_broken_state_not_silently_reset(self):
        state_path(self.path).write_text('broken')
        with self.assertRaises(ConfigError):choices(read_snapshot(self.path))
if __name__=='__main__':unittest.main()
