"""First-use, help and recovery paths using local fake data only."""
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
from provider_core import ConfigError
from provider_presets import KEY_GUIDES

with tempfile.TemporaryDirectory(dir=base/'test-temp') as scratch:
    config=Path(scratch)/'config.toml'
    root=tk.Tk();app=App(root,config);root.geometry('980x700');root.update()
    assert app.tabs.select()==5 and not config.exists()
    for widget in (app.welcome_account,app.welcome_start):
        canvas=app.tabs.pages[5][1]
        assert canvas.winfo_rooty()<=widget.winfo_rooty()
        assert widget.winfo_rooty()+widget.winfo_height()<=canvas.winfo_rooty()+canvas.winfo_height()
    ImageGrab.grab(window=root.winfo_id()).save(base/'ui-onboarding.png')
    app.welcome_account.invoke();wait_profiles(app);root.update()
    assert app.tabs.select()==4 and 'account' in app.switch_buttons and not config.exists()
    assert app.welcome_marker.read_text(encoding='utf-8')=='welcome-seen-v1\n'
    app.tabs.select(5);app.welcome_start.invoke();root.update()
    assert app.tabs.select()==0
    app.welcome_marker.write_text('existing marker',encoding='utf-8')
    app.finish_welcome(0)
    assert app.welcome_marker.read_text(encoding='utf-8')=='existing marker'
    with patch('desktop_ui.webbrowser.open') as browser:
        app.key_help_button.invoke();root.update()
        browser.assert_not_called()
        assert 'DeepSeek' in app.key_help_text.get('1.0','end')
        ImageGrab.grab(window=app.key_help_window.winfo_id()).save(base/'ui-key-help.png')
        app.key_console_button.invoke()
        browser.assert_called_once_with(KEY_GUIDES['DeepSeek'])
        root.tk.call(app.key_help_window.protocol('WM_DELETE_WINDOW'));root.update()
        app.provider_group_buttons['自定义模型'].invoke();app.key_help_button.invoke();root.update()
        assert app.key_console_button is None and 'Responses' in app.key_help_text.get('1.0','end')
        root.tk.call(app.key_help_window.protocol('WM_DELETE_WINDOW'));root.update()
    app.tabs.select(3);root.update()
    assert not app.advanced_content.winfo_ismapped()
    ImageGrab.grab(window=root.winfo_id()).save(base/'ui-settings-simple.png')
    app.vars['name'].set('保留草稿')
    app.advanced_toggle.invoke();root.update()
    assert app.advanced_config_entry.winfo_ismapped()
    app.advanced_toggle.invoke();root.update()
    assert not app.advanced_config_entry.winfo_ismapped() and app.vars['name'].get()=='保留草稿'
    with patch('app.messagebox.showerror') as errors:
        app.show_error(ConfigError('HTTP 401：FAKE-PRIVATE-KEY'))
        root.update()
        assert app.error_action_button.winfo_rootx()+app.error_action_button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
        assert 'FAKE-PRIVATE' not in errors.call_args.args[1]
        # invoke() and the mocked dialog do not activate the window as a real click would.
        # Establish that precondition before asserting the OS keyboard focus.
        root.focus_force();root.update()
        app.error_action_button.invoke();root.update()
        assert app.tabs.select()==0 and root.focus_get()==app.token_entry, (
            app.tabs.select(), str(root.focus_get()), str(root.focus_lastfor()), str(app.token_entry))
        app.show_error(ConfigError('配置不是有效的 UTF-8 TOML'))
        root.focus_force();root.update()
        app.error_action_button.invoke();root.update()
        assert app.tabs.select()==3 and app.advanced_config_entry.winfo_ismapped()
        assert root.focus_get()==app.advanced_config_entry
        app.show_error(ConfigError('HTTP 429：private'))
        app.vars['model'].set('changed')
        assert not app.error_action_button.winfo_manager()
    assert not config.exists()
    root.destroy()
    config.write_text('model="existing"\n',encoding='utf-8')
    root=tk.Tk();app=App(root,config);root.update()
    assert app.tabs.select()==0
    app.guide_button.invoke();root.update()
    assert app.tabs.select()==5 and config.read_text(encoding='utf-8')=='model="existing"\n'
    root.destroy()
    # Existing Codex users still see the introduction on their first tool launch.
    existing=Path(scratch)/'existing'/'config.toml'
    existing.parent.mkdir();existing.write_text('model="existing"\n',encoding='utf-8')
    root=tk.Tk();app=App(root,existing);root.update()
    assert app.tabs.select()==5
    assert existing.read_text(encoding='utf-8')=='model="existing"\n'
    root.destroy()
print('PASS: first-use and existing-config entry, account navigation without writes, key help before external link, custom help, advanced collapse, recovery focus, redaction and unchanged fixtures.')
