from ui_test_support import wait_profiles
from pathlib import Path
import tempfile
import sys
import tkinter as tk
from unittest.mock import patch

base=Path(__file__).resolve().parent
sys.path.insert(0,str(base.parents[1]/'src'))
from app import App
from provider_core import parse_config

with tempfile.TemporaryDirectory(dir=base/'test-temp') as scratch:
    config=Path(scratch)/'config.toml'
    config.write_text('model="existing"\nmodel_provider="team_gateway"\n[model_providers.team_gateway]\nname="Team"\nbase_url="https://example.com/v1"\nenv_key="TEAM_KEY"\n',encoding='utf-8')
    root=tk.Tk();app=App(root,config,show_welcome=False);root.update()
    def fail(title,text,**kwargs):raise AssertionError(text)
    with patch('app.messagebox.showerror',side_effect=fail):
        app.load_current()
        assert app.vars['provider'].get()=='team_gateway'
        app.vars['model'].set('another-model')
        app.vars['name'].set('中文显示名称')
        app.make_preview();wait_profiles(app)
        assert parse_config(app.plan.updated)['model_provider']=='team_gateway'
        assert app.provider_entry.cget('state')=='readonly'
        app.vars['base_url'].set('https://new.example.com/v2')
        app.make_preview();wait_profiles(app)
        generated=app.vars['provider'].get()
        assert generated!='team_gateway'
        parsed=parse_config(app.plan.updated)
        assert parsed['model_providers']['team_gateway']['base_url']=='https://example.com/v1'
        assert parsed['model_provider']==generated
        app.vars['model'].set('third-model')
        app.vars['name'].set('再次改名')
        app.make_preview();wait_profiles(app)
        assert app.vars['provider'].get()==generated
        assert not app.save_button.instate(['disabled'])
        assert 'new.example.com' not in config.read_text()
        config.write_text('model="deepseek-flash"\nmodel_provider="deepseek_1"\n[model_providers.deepseek_1]\nname="DeepSeek"\nbase_url="https://api.deepseek.com"\nenv_key="DEEPSEEK_API_KEY"\n',encoding='utf-8')
        app.load_current()
        assert app.vars['preset'].get()=='DeepSeek'
        assert app.vars['provider'].get()=='deepseek_1'
    root.destroy()
print('PASS: automatic IDs, read-only identifier, loaded ID reuse, URL changes isolate services, names/models do not rename IDs; no config writes.')
