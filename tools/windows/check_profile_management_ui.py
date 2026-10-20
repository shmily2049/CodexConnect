from ui_test_support import wait_profiles
from pathlib import Path
import sys,tempfile,tkinter as tk
from dataclasses import replace
from unittest.mock import patch
from PIL import ImageGrab
base=Path(__file__).resolve().parent;sys.path.insert(0,str(base.parents[1]/'src'))
from app import App
from provider_core import *
from switch_profiles import choices
with tempfile.TemporaryDirectory(dir=base/'test-temp') as temp:
    config=Path(temp)/'config.toml';config.write_text('model="account"\n')
    settings=Settings('fixture','First','a','https://example.com/v1',auth_mode='token',token='FAKE-EDIT-KEY')
    apply_plan(prepare(read_snapshot(config),settings));apply_plan(prepare(read_snapshot(config),replace(settings,model='b',name='Second')))
    root=tk.Tk();app=App(root,config,show_welcome=False)
    def fail(title,message,**kwargs):raise AssertionError(message)
    with patch('app.messagebox.showerror',side_effect=fail),patch('app.messagebox.showinfo'):
        app.tabs.select(4);wait_profiles(app);root.update()
        a=next(x for x in app.profile_choices if x['fields'].get('model')=='a')
        b=next(x for x in app.profile_choices if x['fields'].get('model')=='b')
        assert 'account' not in app.edit_buttons and app.delete_buttons[b['id']].instate(['disabled'])
        original=config.read_bytes()
        with patch('app.messagebox.askyesno',return_value=False):app.delete_buttons[a['id']].invoke();wait_profiles(app)
        assert config.read_bytes()==original and len(app.profile_choices)==3
        app.edit_buttons[a['id']].invoke();wait_profiles(app);root.update()
        assert app.edit_banner.winfo_ismapped() and app.vars['name'].get()=='First'
        assert app.vars['token'].get()=='' and app.settings().token=='FAKE-EDIT-KEY'
        app.cancel_edit();wait_profiles(app);root.update();assert config.read_bytes()==original
        app.edit_buttons[a['id']].invoke();wait_profiles(app);app.vars['base_url'].set('https://different.example/v1')
        try:app.settings();raise AssertionError('Old key reused for another host')
        except ConfigError:pass
        app.vars['base_url'].set(settings.base_url);app.vars['name'].set('Edited');app.vars['model'].set('edited-model')
        assert app.vars['catalog'].get()==''
        app.make_preview();wait_profiles(app);root.update();assert app.plan and 'FAKE-EDIT-KEY' not in app.plan.preview
        with patch('app.messagebox.askyesno',return_value=True):app.save();wait_profiles(app)
        app.tabs.select(4);wait_profiles(app);root.update()
        assert not any(x['id']==a['id'] for x in app.profile_choices)
        assert parse_config(config.read_bytes())['model']=='edited-model'
        with patch('app.messagebox.askyesno',return_value=True):app.delete_buttons[b['id']].invoke();wait_profiles(app)
        app.refresh_profiles();wait_profiles(app);assert len(app.profile_choices)==2
        root.geometry('980x700');root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base/'ui-profile-management.png')
    root.destroy()
print('PASS: edit, cancel, key retention, changed-address isolation, replacement, deletion persistence and compact cards.')
