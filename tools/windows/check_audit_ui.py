"""Offline regression for review fixes, dirty forms, saved tests and compact layouts."""
from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from app import App
from provider_core import VERSION, Settings, prepare, apply_plan, read_snapshot, parse_config, suggested_provider_id
from switch_profiles import choices

OUT = ROOT / ('work/fix-' + VERSION)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'temp').mkdir(exist_ok=True)

def fail(title, message, **kwargs):
    raise AssertionError(message)

with tempfile.TemporaryDirectory(dir=OUT / 'temp') as temp:
    config = Path(temp) / 'config.toml'
    config.write_text('model="account-model"\n')
    settings = Settings(suggested_provider_id('https://example.com/v1'), 'First', 'a', 'https://example.com/v1', auth_mode='token', token='FAKE-AUDIT-KEY')
    apply_plan(prepare(read_snapshot(config), settings))
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    with patch('app.messagebox.showerror', side_effect=fail), patch('app.messagebox.showinfo'), patch('app.messagebox.askyesno', return_value=True) as ask:
        app.tabs.select(4);wait_profiles(app)
        a = next(i for i in app.profile_choices if i['current'])
        app.edit_profile(a['id'], str(config.resolve()));wait_profiles(app)
        app.vars['model'].set('unsaved')
        with patch('app.messagebox.askyesno', return_value=False):
            app.close_window()
            assert root.winfo_exists()
            app.choose_preset('Kimi')
            assert app.vars['model'].get() == 'unsaved'
            app.tabs.select(4);wait_profiles(app)
            app.add_model_button.invoke()
            assert app.editing_profile is not None
        app.add_model_button.invoke()
        assert app.editing_profile is None and app.plan is None and app.vars['token'].get() == ''
        app.vars['model'].set('new-model')
        app.vars['base_url'].set('https://example.com/v1')
        app.vars['token'].set('FAKE-AUDIT-KEY')
        app.make_preview();wait_profiles(app)
        app.save();wait_profiles(app)
        assert any(i['id'] == a['id'] for i in choices(read_snapshot(config)))
        assert app.vars['token'].get() == ''
        assert app.form_signature() == app.clean_form
        assert '可恢复' in app.backup_list.get(0)
        with patch.object(app, 'background') as background:
            app.saved_test_button.invoke()
            fn, callback, _ = background.call_args.args
            with patch('app.test_connection', return_value='fixture response') as test:
                assert fn() == 'fixture response'
                assert test.call_args.args[0].token == 'FAKE-AUDIT-KEY'
                assert test.call_args.args[0].model == 'new-model'
            assert app.vars['token'].get() == ''
            callback('fixture response')
        # Credential edits explicitly name other affected models.
        app.edit_profile(a['id'], str(config.resolve()));wait_profiles(app)
        app.vars['token'].set('FAKE-REPLACEMENT')
        app.make_preview();wait_profiles(app)
        app.save();wait_profiles(app)
        assert any('new-model' in call.args[1] and '共用密钥' in call.args[1] for call in ask.call_args_list)
        # URL reset is reviewed in the final confirmation, never silently applied.
        doc = parse_config(config.read_bytes())
        doc['openai_base_url'] = 'https://proxy.example/v1'
        import tomlkit
        config.write_text(tomlkit.dumps(doc), encoding='utf-8')
        original = config.read_bytes()
        with patch('app.messagebox.askyesno', return_value=False):
            app.switch_profile('account', str(config.resolve()))
            wait_profiles(app)
        assert config.read_bytes() == original
        app.switch_profile('account', str(config.resolve()))
        wait_profiles(app)
        assert 'openai_base_url' not in parse_config(config.read_bytes())
        assert any('移除该地址覆盖' in call.args[1] for call in ask.call_args_list)
        root.geometry('860x580')
        root.update()
        app.tabs.select(4);wait_profiles(app)
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(OUT / 'compact-models.png')
    root.destroy()

    for scaling in (1.333, 2.0, 2.666):
        root = tk.Tk()
        root.tk.call('tk', 'scaling', scaling)
        app = App(root, config, show_welcome=False)
        root.geometry('980x700')
        root.update()
        canvas = app.tabs.pages[0][1]
        canvas.yview_moveto(1)
        root.update()
        assert app.test_button.winfo_rootx() + app.test_button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
        assert app.test_button.winfo_rooty() + app.test_button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        root.focus_force()
        app.model_entry.focus_force()
        root.update()
        assert app.model_entry.winfo_rooty() >= canvas.winfo_rooty()
        ImageGrab.grab(window=root.winfo_id()).save(OUT / f'scaling-{scaling}.png')
        root.destroy()
print('PASS: add-vs-edit, dirty protection, saved-key tests, shared credential notice, explicit URL reset, backups, 860x580 and 100/150/200% Tk scaling. No network.')
