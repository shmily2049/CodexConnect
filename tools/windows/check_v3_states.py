from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from app import App, ConfigError

with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    root = tk.Tk()
    app = App(root, Path(scratch) / 'config.toml', show_welcome=False)
    root.update()
    with patch('app.messagebox.askyesno',return_value=True), patch('app.messagebox.showinfo'), patch('app.messagebox.showerror'):
        app.provider_group_buttons['自定义模型'].invoke()
        assert app.vars['preset'].get() == '自定义 Responses 服务'
        app.vars['model'].set('mock-model')
        app.vars['base_url'].set('https://example.com/v1')
        app.auth_buttons[1].invoke()
        assert app.vars['auth'].get() == 'API Key 保存到配置文件'
        app.vars['token'].set('FAKE-KEY-NOT-A-CREDENTIAL')
        app.auth_buttons[0].invoke()
        assert app.vars['token'].get() == ''
        assert app.summary_auth.get() == '环境变量'
        # Capture callbacks instead of contacting the API or provider site.
        pending=[]
        def hold(fn, callback, label): pending.append(callback)
        with patch.object(app,'background',side_effect=hold):
            app.test_api()
            assert app.connection_state.get() == '正在测试连接…'
            pending.pop()('mock successful response')
            assert app.connection_state.get() == '文本请求已通过'
            app.vars['model'].set('changed-model')
            assert app.connection_state.get() == '尚未测试连接'
            app.test_api()
            app.vars['model'].set('newer-model')
            pending.pop()('stale mock response')
            assert app.connection_state.get() == '尚未测试连接'
            assert '配置已变更' in app.status.get()
            app.fetch_catalog()
            app.vars['model'].set('newest-model')
            pending.pop()(b'not used')
            assert app.catalog_bytes is None
            assert '未应用返回结果' in app.status.get()
        app.testing_revision=app.revision
        app.events.put((lambda value: None,None,ConfigError('Mock failure'),app.revision))
        app.poll()
        assert app.connection_state.get() == '连接测试未通过'
        app.save_button.configure(state='disabled')
        with patch.object(app.save_button,'command') as command:
            app.save_button.invoke()
            command.assert_not_called()
        # Keyboard activation must work without the mouse.
        app.tabs.buttons[3].focus_force()
        root.update()
        app.tabs.buttons[3].event_generate('<Return>')
        root.update()
        assert app.tabs.select() == 3
        assert not (Path(scratch)/'config.toml').exists()
    root.destroy()
print('PASS: provider and auth controls, keyboard navigation, disabled save, connection status invalidation, stale network results. No network/config writes.')
