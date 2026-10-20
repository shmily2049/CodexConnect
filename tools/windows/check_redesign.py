from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from app import App

def fail(title, text, **kwargs):
    raise AssertionError(text)

with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    config = Path(scratch) / 'config.toml'
    original = '# keep this comment\nmodel="old"\n[desktop]\nlocaleOverride="zh-CN"\n'
    config.write_text(original, encoding='utf-8')
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    with patch('app.messagebox.askyesno', return_value=True), patch('app.messagebox.showinfo'), patch('app.messagebox.showerror', side_effect=fail):
        root.update()
        assert app.token_group.winfo_ismapped() and not app.env_group.winfo_ismapped()
        assert app.provider_entry.cget('state') == 'readonly'
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-config.png')
        for n in (3, 1, 2, 0):
            app.tabs.buttons[n].invoke()
            root.update()
            assert app.tabs.select() == n
        app.tabs.select(3)
        app.set_advanced(True)
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-advanced.png')
        canvas = app.tabs.pages[3][1]
        canvas.yview_moveto(1)
        root.update()
        assert app.catalog_fetch_button.winfo_rooty() + app.catalog_fetch_button.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
        app.tabs.select(2)
        app.refresh_backups();wait_profiles(app)
        assert '暂无备份' in app.backup_state.get()
        app.tabs.select(0)
        app.vars['preset'].set('自定义 Responses 服务')
        app.preset_changed()
        app.vars['model'].set('local-test-model')
        app.vars['base_url'].set('https://example.com/v1')
        app.vars['auth'].set('API Key 保存到配置文件')
        app.auth_changed()
        root.update()
        assert app.token_group.winfo_ismapped() and not app.env_group.winfo_ismapped()
        app.vars['token'].set('FAKE-UI-TEST-KEY')
        app.make_preview();wait_profiles(app)
        assert app.plan is not None
        assert 'FAKE-UI-TEST-KEY' not in app.preview_text.get('1.0', 'end')
        app.vars['model'].set('edited-model')
        assert app.plan is None and app.save_button.instate(['disabled'])
        app.vars['auth'].set('环境变量（推荐）')
        app.auth_changed()
        assert not app.vars['token'].get()
        app.make_preview();wait_profiles(app)
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-preview.png')
        assert config.read_text(encoding='utf-8') == original
        app.save();wait_profiles(app)
        assert 'edited-model' in config.read_text(encoding='utf-8')
        app.load_current()
        assert app.vars['model'].get() == 'edited-model'
        app.tabs.select(2)
        app.refresh_backups();wait_profiles(app)
        assert len(app.backups) == 1
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-backups.png')
        app.backup_list.selection_set(0)
        app.restore()
        assert config.read_text(encoding='utf-8') == original
        app.tabs.select(0)
        root.geometry('980x700')
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-compact.png')
        canvas = app.tabs.pages[0][1]
        canvas.yview_moveto(1)
        root.update()
        assert app.test_button.winfo_rootx() + app.test_button.winfo_width() <= canvas.winfo_rootx() + canvas.winfo_width()
        footer = app.tabs.footers[0]
        assert app.test_button.winfo_rooty() >= footer.winfo_rooty()
        assert app.test_button.winfo_rooty() + app.test_button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
    root.destroy()
print('PASS: navigation, scroll at minimum size, auth switching, masking, stale preview, save, load and restore. Isolated config only.')
