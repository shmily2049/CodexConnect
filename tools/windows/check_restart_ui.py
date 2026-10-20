from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab
base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from app import App
from provider_core import Settings, prepare, apply_plan, read_snapshot, parse_config, ConfigError
from desktop_restart import DesktopTarget


with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    config = Path(scratch) / 'config.toml'
    config.write_text('model="account-model"\n', encoding='utf-8')
    apply_plan(prepare(read_snapshot(config), Settings('fake','演示模型','model-a','https://example.com',auth_mode='token',token='FAKE')))
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    target = DesktopTarget('win32','FAKE','演示桌面')
    def pump():
        deadline = time.monotonic() + 4
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert not app.busy and not app.restart_running
    with patch('app.messagebox.showinfo'), patch('app.messagebox.askyesno',return_value=True), patch('app.messagebox.showerror') as errors:
        app.tabs.select(4);wait_profiles(app)
        app.auto_restart.set(True)
        before = config.read_bytes()
        with patch('app.discover_desktop', side_effect=ConfigError('not found')), patch('app.restart_desktop') as restart:
            app.switch_profile('account',str(config))
            pump()
            assert config.read_bytes() == before
            restart.assert_not_called()
            errors.assert_called_once()
        errors.reset_mock()
        def restarted(target):
            assert parse_config(config.read_bytes())['model_provider'] == 'openai'
            return '模拟重启成功'
        with patch('app.discover_desktop',return_value=target), patch('app.restart_desktop',side_effect=restarted) as restart:
            app.switch_profile('account',str(config))
            deadline = time.monotonic() + 4
            while not app.restart_running and time.monotonic() < deadline:
                root.update()
                time.sleep(.005)
            assert app.restart_running
            app.close_window()
            assert root.winfo_exists()
            pump()
            restart.assert_called_once()
            assert '已重新打开' in app.footer_note.get()
        with patch('app.discover_desktop',return_value=target), patch('app.restart_desktop',side_effect=ConfigError('simulated timeout')), patch('app.messagebox.showwarning') as warning:
            app.restart_codex()
            pump()
            warning.assert_called_once()
            assert '配置已保留' in app.footer_note.get()
        errors.assert_not_called()
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save(base / 'ui-restart.png')
    root.destroy()
print('PASS: preflight failure leaves config unchanged, save before restart, async success/failure, no real desktop exit.')
