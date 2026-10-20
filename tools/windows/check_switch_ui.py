from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from dataclasses import replace
from PIL import ImageGrab

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from app import App
from provider_core import Settings, prepare, apply_plan, read_snapshot, parse_config


def fail(title, text, **kwargs):
    raise AssertionError(text)


with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    config = Path(scratch) / 'config.toml'
    config.write_text('model="account-model"\n', encoding='utf-8')
    s = Settings('gateway', '我的模型服务', 'model-a', 'https://example.com/v1',
                 auth_mode='token', token='FAKE-UI-KEY')
    apply_plan(prepare(read_snapshot(config), s))
    apply_plan(prepare(read_snapshot(config), replace(s, model='model-b')))
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    with patch('app.messagebox.showinfo'), patch('app.messagebox.showerror', side_effect=fail):
        app.tabs.buttons[4].invoke();wait_profiles(app)
        root.update()
        assert len(app.switch_buttons) == 3
        b = next(p for p in app.profile_choices if p['fields'].get('model') == 'model-b')
        assert 'model-b' in app.selected_model.get()
        assert app.switch_buttons[b['id']].instate(['disabled'])
        assert app.switch_buttons[b['id']].text == '✓ 已选择'
        assert app.profile_container.winfo_children()[0] == app.profile_cards[b['id']]
        with patch.object(app, 'switch_profile') as switch:
            app.switch_buttons[b['id']].invoke()
            switch.assert_not_called()
        before = config.read_bytes()
        with patch('app.messagebox.askyesno', return_value=False):
            app.switch_buttons['account'].invoke();wait_profiles(app)
        assert before == config.read_bytes()
        with patch('app.messagebox.askyesno', return_value=True):
            app.switch_buttons['account'].invoke();wait_profiles(app)
            assert parse_config(config.read_bytes())['forced_login_method'] == 'chatgpt'
            assert app.selected_model.get() == 'ChatGPT套餐'
            assert app.switch_buttons['account'].instate(['disabled'])
            assert app.switch_buttons[b['id']].instate(['!disabled'])
            a = next(p for p in app.profile_choices if p['fields'].get('model') == 'model-a')
            app.switch_buttons[a['id']].invoke();wait_profiles(app)
            assert parse_config(config.read_bytes())['model'] == 'model-a'
            assert app.plan is None
            assert 'model-a' in app.selected_model.get()
            assert app.switch_buttons[a['id']].instate(['disabled'])
            assert app.switch_buttons['account'].instate(['!disabled'])
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-switch.png')
        root.geometry('980x700')
        root.update()
        canvas = app.tabs.pages[4][1]
        canvas.yview_moveto(1)
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-switch-compact.png')
        with patch('app.read_snapshot', side_effect=OSError('fixture unreadable')), patch.object(app, 'show_error'):
            app.refresh_profiles();wait_profiles(app)
        assert not app.switch_buttons
        assert '无法读取' in app.selected_model.get()
    root.destroy()
print('PASS: saved models, cancel, account return, model switch, stale preview invalidated, compact layout. Fake configuration only.')
