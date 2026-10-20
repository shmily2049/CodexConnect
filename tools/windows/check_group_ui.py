from ui_test_support import wait_profiles
"""Group defaults, remembered choices and atomic discard protection; fixture only."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from app import App
from provider_presets import PRESETS, get_preset
from provider_core import VERSION

with tempfile.TemporaryDirectory() as scratch:
    config=Path(scratch)/'config.toml'
    original=b'# fixture only\nmodel="existing"\n'
    config.write_bytes(original)
    root=tk.Tk(); app=App(root,config,show_welcome=False); root.update()
    failures=[]
    root.report_callback_exception=lambda *args:failures.append(args)
    with patch('app.messagebox.showerror',side_effect=AssertionError), patch('app.messagebox.askyesno',return_value=True):
        for group in ('国内模型','国际模型'):
            members=[p for p in PRESETS if p.group==group]
            app.provider_group_buttons[group].invoke(); root.update()
            assert app.vars['preset'].get()==members[0].key
            assert app.vars['model'].get()==members[0].routes[0].models[0]
            assert app.visible_provider_group==group
            second=members[1]
            next(t for t in app.provider_tiles if t.preset_key==second.key).invoke()
            app.provider_group_buttons['自定义模型'].invoke()
            app.provider_group_buttons[group].invoke(); root.update()
            assert app.vars['preset'].get()==second.key
            assert app.vars['model'].get()==second.routes[0].models[0]
        # A valid preview and its input must survive a cancelled group switch.
        app.vars['token'].set('FAKE-GROUP-KEY')
        app.make_preview();wait_profiles(app)
        assert app.plan is not None
        app.tabs.select(0); root.update()
        plan=app.plan; signature=app.form_signature(); revision=app.revision
        selected=app.vars['preset'].get(); group=app.visible_provider_group
        remembered=dict(app.last_group_presets)
        with patch('app.messagebox.askyesno',return_value=False) as ask:
            for target in ('国内模型','自定义模型'):
                app.provider_group_buttons[target].invoke(); root.update()
                assert app.visible_provider_group==group
                assert app.vars['preset'].get()==selected
                assert app.form_signature()==signature and app.plan is plan
                assert app.revision==revision and app.last_group_presets==remembered
            assert ask.call_count==2
            app.provider_group_buttons[group].invoke(); root.update()
            assert ask.call_count==2 and app.plan is plan
        app.provider_group_buttons['国内模型'].invoke(); root.update()
        assert app.vars['token'].get()=='' and app.plan is None
        assert app.save_button.instate(['disabled'])
        # Loading a provider through another UI route also updates group memory.
        app.vars['preset'].set('OpenAI API'); app.preset_changed()
        app.provider_group_buttons['国内模型'].invoke()
        app.provider_group_buttons['国际模型'].invoke(); root.update()
        assert app.vars['preset'].get()=='OpenAI API'
        assert config.read_bytes()==original
        assert not (config.parent/'provider-tool-backups').exists()
        root.geometry('980x700'); root.update()
        out=ROOT/f'work/fix-{VERSION}';out.mkdir(parents=True,exist_ok=True)
        ImageGrab.grab(window=root.winfo_id()).save(out/'group-selection.png')
        assert not failures,failures
    root.destroy()
print('PASS: first default, per-group memory, synchronized form, cancelled tab/form/preview unchanged, same-tab no-op, key clearing, no config writes.')
