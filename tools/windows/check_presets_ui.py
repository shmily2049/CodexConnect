from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab
base=Path(__file__).resolve().parent
sys.path.insert(0,str(base.parents[1]/'src'))
from app import App
from provider_presets import PRESETS
from provider_core import parse_config, apply_plan, ConfigError


def fail(title,text,**kwargs):raise AssertionError(text)


with tempfile.TemporaryDirectory(dir=base/'test-temp') as scratch:
    config=Path(scratch)/'config.toml'
    root=tk.Tk();app=App(root,config,show_welcome=False);root.update()
    with patch('app.messagebox.showerror',side_effect=fail), patch('app.messagebox.askyesno',return_value=True):
        for preset in PRESETS:
            if preset.key=='DeepSeek':continue
            app.vars['token'].set('FAKE-PREVIOUS-KEY')
            if preset.group == '自定义模型':
                app.provider_group_buttons['自定义模型'].invoke()
            else:
                next(t for t in app.provider_tiles if t.preset_key==preset.key).invoke()
            assert app.vars['token'].get()==''
            assert app.catalog_bytes is None and app.vars['catalog'].get()==''
            for route in preset.routes:
                app.vars['workspace'].set('')
                app.vars['route'].set(route.label);app.route_changed()
                if '{workspace}' in route.url:
                    assert app.vars['base_url'].get()==''
                    app.vars['workspace'].set('team-123')
                    assert 'team-123.' in app.vars['base_url'].get()
                if not route.url:
                    app.vars['base_url'].set('https://example.com/v1')
                    app.vars['model'].set('custom-model')
                app.vars['token'].set('FAKE-KEY')
                app.make_preview();wait_profiles(app)
                assert app.plan is not None
                assert 'FAKE-KEY' not in app.plan.preview
                doc=parse_config(app.plan.updated)
                assert doc['model_providers'][doc['model_provider']]['base_url']==app.vars['base_url'].get()
        app.vars['preset'].set('通义千问');app.preset_changed()
        app.vars['workspace'].set('team-123');app.vars['token'].set('FAKE-KEY')
        app.make_preview();wait_profiles(app);apply_plan(app.plan)
        app.load_current()
        assert app.vars['preset'].get()=='通义千问'
        assert app.vars['workspace'].get()=='team-123'
        assert app.vars['base_url'].get().startswith('https://team-123.')
        assert app.vars['token'].get()==''
        app.vars['token'].set('FAKE-KEY');app.vars['workspace'].set('other-team')
        assert app.vars['token'].get()=='' and app.plan is None
        app.vars['preset'].set('Claude · OpenRouter');app.preset_changed()
        app.vars['token'].set('sk-ant-FAKE')
        try:app.settings();raise AssertionError('wrong credential accepted')
        except ConfigError:pass
        app.vars['token'].set('')
        app.tabs.select(0);root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base/'ui-presets-global.png')
        root.geometry('980x700');root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base/'ui-presets-compact.png')
    root.destroy()
print('PASS: every preset/route previews, keys cleared, workspace URL, loaded route, wrong gateway key blocked, UI layout. No external requests.')
