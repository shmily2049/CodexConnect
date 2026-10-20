from ui_test_support import wait_profiles
"""Information hierarchy and minimum-window interaction, isolated fake config."""
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

with tempfile.TemporaryDirectory(dir=base/'test-temp') as scratch:
    config=Path(scratch)/'config.toml'
    root=tk.Tk();app=App(root,config,show_welcome=False);root.geometry('980x700');root.update()
    sidebar=app.tabs.buttons[0].master
    assert {n for n,b in app.tabs.buttons.items() if b.master==sidebar}=={0,3,4}
    canvas=app.tabs.pages[0][1]
    for widget in (app.model_entry,app.token_entry,app.paste_button):
        assert widget.winfo_rooty()>=canvas.winfo_rooty()
        assert widget.winfo_rooty()+widget.winfo_height()<=canvas.winfo_rooty()+canvas.winfo_height()
    app.show_provider_group('国际模型');root.update()
    assert app.summary_name.get()=='DeepSeek' and app.vars['preset'].get()=='DeepSeek'
    app.vars['token'].set('FAKE-PREVIOUS-KEY')
    app.provider_group_buttons['自定义模型'].invoke();root.update()
    assert app.vars['preset'].get()=='自定义 Responses 服务' and not app.vars['token'].get()
    assert app.base_url_entry.winfo_ismapped() and app.token_entry.winfo_ismapped()
    assert not any(t.winfo_ismapped() for t in app.provider_tiles)
    app.vars['model'].set('custom-draft');app.vars['base_url'].set('https://example.com/v1')
    app.vars['token'].set('FAKE-CUSTOM-KEY')
    app.provider_group_buttons['自定义模型'].invoke();root.update()
    assert app.vars['model'].get()=='custom-draft' and app.vars['token'].get()=='FAKE-CUSTOM-KEY'
    ImageGrab.grab(window=root.winfo_id()).save(base/'ui-custom-direct.png')
    app.provider_group_buttons['国内模型'].invoke();root.update()
    assert any(t.winfo_ismapped() for t in app.provider_tiles)
    for preset in PRESETS:
        app.vars['preset'].set(preset.key);app.preset_changed();root.update()
        if preset.service=='OpenRouter':assert 'OpenRouter' in app.route_note.cget('text') and app.route_note.winfo_ismapped()
        if len(preset.routes)>1:assert app.route_group.winfo_ismapped()
        assert not app.base_url_group.winfo_ismapped() if preset.docs else app.base_url_group.winfo_ismapped()
    app.tabs.buttons[3].invoke();root.update()
    assert not app.advanced_content.winfo_ismapped()
    app.advanced_toggle.invoke();root.update()
    assert app.tabs.buttons[2].winfo_ismapped() and app.auth_buttons[0].winfo_ismapped()
    app.auth_buttons[0].invoke();app.tabs.buttons[0].invoke();root.update()
    assert app.env_group.winfo_ismapped() and not app.token_group.winfo_ismapped()
    app.vars['preset'].set('豆包 / 火山方舟');app.preset_changed();root.update()
    assert '按量付费' in app.route_note.cget('text')
    app.vars['route'].set('Coding Plan 套餐');app.route_changed();root.update()
    assert '专属密钥' in app.route_note.cget('text')
    app.vars['preset'].set('DeepSeek');app.preset_changed();root.update()
    ImageGrab.grab(window=root.winfo_id()).save(base/'ui-minimal-compact.png')
    assert not config.exists()
    app.provider_group_buttons['自定义模型'].invoke();root.update()
    assert app.custom_name_entry.winfo_ismapped()
    app.vars['model'].set('model-a');app.vars['base_url'].set('https://example.com/v1')
    app.vars['token'].set('FAKE-NAMED-KEY');app.vars['name'].set('')
    with patch('app.messagebox.showerror') as error, patch('app.messagebox.askyesno',return_value=True):
        app.make_preview();wait_profiles(app)
        assert app.plan is None and '名称' in error.call_args.args[1]
        app.vars['name'].set('日常编程')
        app.provider_group_buttons['自定义模型'].invoke()
        assert app.vars['name'].get()=='日常编程'
        app.make_preview();wait_profiles(app)
        assert app.plan is not None and '日常编程' in app.preview_summary.get()
        app.save();wait_profiles(app);app.tabs.select(4);wait_profiles(app);root.update()
        assert any(p['label']=='日常编程 · model-a' for p in app.profile_choices)
        ImageGrab.grab(window=root.winfo_id()).save(base/'ui-named-model.png')
        app.load_current()
        assert app.vars['name'].get()=='日常编程'
        app.tabs.select(0);root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base/'ui-custom-named.png')
    root.destroy()
print('PASS: three primary navigation items, compact default fields visible, selected provider retained during browsing, billing and gateway notices, settings access, no configuration writes.')
