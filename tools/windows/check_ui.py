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
    original = '# user comment\nmodel="old"\n[desktop]\nlocaleOverride="zh-CN"\n'
    config.write_text(original, encoding='utf-8')
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    root.update()
    ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-config.png')
    app.vars['preset'].set('自定义 Responses 服务')
    app.preset_changed()
    app.vars['model'].set('local-test-model')
    app.vars['base_url'].set('https://example.com/v1')
    app.vars['token'].set('FAKE-UI-TEST-KEY')
    with patch('app.messagebox.showerror', side_effect=fail):
        app.make_preview();wait_profiles(app)
    root.update()
    assert app.plan is not None
    assert config.read_text(encoding='utf-8') == original
    ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-preview.png')
    with patch('app.messagebox.askyesno', return_value=True), patch('app.messagebox.showinfo'), patch('app.messagebox.showerror', side_effect=fail):
        app.save();wait_profiles(app)
        assert 'local-test-model' in config.read_text(encoding='utf-8')
        app.refresh_backups();wait_profiles(app)
        app.backup_list.selection_set(0)
        app.restore()
        assert config.read_text(encoding='utf-8') == original
    root.destroy()
print('UI launch, preview, save, backup and restore passed using an isolated fixture.')
