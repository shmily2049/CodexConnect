from ui_test_support import wait_profiles
"""Novice paths with fake keys, fake catalog transport, and isolated files only."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import time
from unittest.mock import patch
from PIL import ImageGrab

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from app import App
from provider_core import ConfigError

catalog = b'{"models":[{"slug":"deepseek-flash"}]}'
with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    config = Path(scratch) / 'config.toml'
    original = '# preserve me\n[desktop]\nlocaleOverride="zh-CN"\n'
    config.write_text(original, encoding='utf-8')
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    root.update()
    with patch('app.messagebox.showerror') as errors, patch('app.messagebox.askyesno', return_value=True), patch('app.messagebox.showinfo'):
        # Missing key is actionable and does not start a download.
        with patch('app.fetch_deepseek_catalog') as fetch:
            app.make_preview();wait_profiles(app)
            assert app.plan is None and app.tabs.select() == 0
            assert '不要填写账号密码' in errors.call_args.args[1]
            fetch.assert_not_called()
        with patch.object(root, 'clipboard_get', return_value=' FAKE-KEY-ONLY '):
            app.paste_button.invoke()
        assert app.vars['token'].get() == 'FAKE-KEY-ONLY'
        with patch.object(root, 'clipboard_get', return_value='not a key'):
            app.paste_key()
        assert app.vars['token'].get() == 'FAKE-KEY-ONLY'
        errors.reset_mock()
        # Hold network results: changing provider must discard the old response.
        pending = []
        original_background = app.background
        def hold_catalog(fn, cb, label):
            if '官方文档' in label:
                pending.append(cb)
            else:
                original_background(fn, cb, label)
        with patch.object(app, 'background', side_effect=hold_catalog):
            app.make_preview();wait_profiles(app)
            assert len(pending) == 1 and app.plan is None
            app.vars['preset'].set('Kimi'); app.preset_changed()
            pending.pop()(catalog);wait_profiles(app)
            assert app.plan is None and app.catalog_bytes is None
            app.vars['preset'].set('DeepSeek'); app.preset_changed()
            app.vars['token'].set('FAKE-KEY-ONLY')
            app.make_preview();wait_profiles(app)
            pending.pop()(catalog);wait_profiles(app)
        assert app.plan is not None and app.tabs.select() == 1
        assert config.read_text('utf-8') == original
        assert 'FAKE-KEY-ONLY' not in app.preview_summary.get() + app.preview_text.get('1.0', 'end')
        assert 'DeepSeek' in app.preview_summary.get() and '官方 API' in app.preview_summary.get()
        root.update()
        assert not app.preview_text.winfo_ismapped()
        app.preview_details_button.invoke(); root.update()
        assert app.preview_text.winfo_ismapped()
        app.preview_details_button.invoke()
        # Saving provides next steps, but must never restart on its own.
        with patch('app.discover_desktop') as discover, patch('app.restart_desktop') as restart:
            app.save();wait_profiles(app); root.update()
            assert app.success_panel.winfo_ismapped()
            assert app.plan is None and not app.vars['token'].get()
            discover.assert_not_called(); restart.assert_not_called()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-beginner-saved.png')
        assert len(app.backups) == 1
        assert b'# preserve me' in config.read_bytes()
        app.vars['model'].set('changed')
        root.update()
        assert not app.success_panel.winfo_manager()
        assert app.save_button.instate(['disabled'])
        # Key entry remains visible at the minimum supported window size.
        app.tabs.select(0); root.geometry('980x700')
        app.tabs.pages[0][1].yview_moveto(0); root.update()
        canvas = app.tabs.pages[0][1]
        assert app.token_entry.winfo_rooty() + app.token_entry.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-beginner-compact.png')
        # Workspace and billing choice precede key entry, avoiding accidental re-entry.
        app.vars['preset'].set('通义千问'); app.preset_changed(); root.update()
        assert app.route_entry.winfo_rooty() < app.workspace_entry.winfo_rooty() < app.token_entry.winfo_rooty()
        app.make_preview();wait_profiles(app)
        assert '工作空间编号' in errors.call_args.args[1]
        app.vars['workspace'].set('example-workspace');app.vars['token'].set('FAKE-KEY-ONLY')
        app.make_preview();wait_profiles(app)
        assert app.plan is not None
        errors.reset_mock()
        # A failed catalog download can be retried, and never changes config.
        app.vars['preset'].set('DeepSeek');app.preset_changed();app.vars['token'].set('FAKE-KEY-ONLY')
        before=config.read_bytes()
        with patch.object(app, 'background', side_effect=hold_catalog):
            app.make_preview();wait_profiles(app)
            app.events.put((pending.pop(),None,ConfigError('获取失败，请检查网络后重试。'),app.revision))
            app.poll()
            assert app.plan is None and app.catalog_bytes is None and config.read_bytes()==before
            app.make_preview();wait_profiles(app);pending.pop()(catalog);wait_profiles(app)
        assert app.plan is not None
        # Exercise the real background queue with a mocked transport as well.
        app.vars['preset'].set('DeepSeek');app.preset_changed();app.vars['token'].set('FAKE-KEY-ONLY')
        with patch('app.fetch_deepseek_catalog', return_value=catalog) as fetch:
            app.make_preview();wait_profiles(app)
            deadline=time.monotonic()+3
            while app.plan is None and time.monotonic()<deadline:
                root.update();time.sleep(.02)
            assert app.plan is not None and not app.busy
            fetch.assert_called_once_with()
    root.destroy()
print('PASS: actionable missing fields, explicit masked paste, automatic catalog preview, stale/failure/retry, plain-language summary, optional details, save next steps, no automatic restart, compact visibility. Fake credentials only.')
