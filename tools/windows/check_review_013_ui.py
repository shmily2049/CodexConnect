"""Five review regressions, real Tk responsiveness and recovery UX; fixtures only."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab
from ui_test_support import wait_profiles

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from app import App
from provider_core import Settings, ConfigError, prepare, apply_plan, read_snapshot, parse_config
from profile_store import delete_choice, resolve_choices, state_path
from switch_profiles import choices
import tomlkit

with tempfile.TemporaryDirectory(prefix='review-013-') as temp:
    base = Path(temp)
    def fixture(name, env=False):
        config = base / name / 'config.toml'
        config.parent.mkdir()
        config.write_text('model="account"\n')
        setting = Settings('fixture', 'Fixture', 'model-a', 'https://old.example/v1',
                           auth_mode='env' if env else 'token', env_key='OLD_FIXTURE_KEY', token='FAKE-OLD')
        apply_plan(prepare(read_snapshot(config), setting))
        apply_plan(prepare(read_snapshot(config), replace(setting, model='model-b')))
        return config

    root = tk.Tk()
    config = fixture('main', env=True)
    app = App(root, config, show_welcome=False)
    callbacks = []
    root.report_callback_exception = lambda *args: callbacks.append(args)
    timings = {}
    with patch('app.messagebox.showerror') as errors, patch('app.messagebox.showinfo'), \
         patch('app.messagebox.askyesno', return_value=True), patch('app.test_connection') as network:
        app.tabs.select(4); wait_profiles(app)
        old = next(x for x in app.profile_choices if x['fields'].get('model') == 'model-a')
        app.edit_profile(old['id'], str(config.resolve())); wait_profiles(app)
        assert app.settings().env_key == 'OLD_FIXTURE_KEY'
        app.vars['base_url'].set('https://different.example/v1')
        app.test_api(); wait_profiles(app)
        network.assert_not_called()
        assert '重新连接' in errors.call_args.args[0]
        app.vars['base_url'].set(old['url'])
        # Failed load must retain the whole edit context, valid preview and test state.
        app.make_preview(); wait_profiles(app)
        app.connection_state.set('文本请求已通过')
        previous = (app.editing_profile, app.editing_state, app.loaded_provider, app.plan, app.form_signature())
        with patch('app.read_snapshot', side_effect=PermissionError('FAKE-PRIVATE')):
            app.load_current()
        assert previous == (app.editing_profile, app.editing_state, app.loaded_provider, app.plan, app.form_signature())
        assert app.connection_state.get() == '文本请求已通过'
        # Delete in another window changes only the registry; editor cannot resurrect it.
        delete_choice(read_snapshot(config), old['id'])
        before = (config.read_bytes(), state_path(config).read_bytes())
        app.make_preview(); wait_profiles(app)
        app.save(); wait_profiles(app)
        assert before == (config.read_bytes(), state_path(config).read_bytes())
        assert not any(x['id'] == old['id'] for x in choices(read_snapshot(config)))
        # Historical provider ID is now used by another URL: never copy its auth settings.
        for mode in ('env', 'token'):
            moved = fixture('moved-' + mode, env=mode == 'env')
            doc = parse_config(moved.read_bytes())
            doc['model_providers']['fixture']['base_url'] = 'https://new.example/v1'
            doc['model_providers']['fixture']['env_key'] = 'NEW_FIXTURE_KEY'
            moved.write_text(tomlkit.dumps(doc), encoding='utf-8')
            app.vars['config'].set(str(moved)); app.tabs.select(4); wait_profiles(app)
            historical = next(x for x in app.profile_choices if x['fields'].get('model') == 'model-a')
            previous = app.editing_profile
            app.edit_profile(historical['id'], str(moved.resolve())); wait_profiles(app)
            assert app.editing_profile == previous
            assert '重新连接' in errors.call_args.args[0]
        # Actual combobox event: cancel/same selection must not invalidate preview.
        app.vars['config'].set(str(config)); app.start_add_model()
        app.choose_preset('豆包 / 火山方舟'); app.vars['token'].set('FAKE-ROUTE')
        app.make_preview(); wait_profiles(app)
        app.connection_state.set('文本请求已通过')
        previous = (app.plan, app.form_signature(), app.revision, app.vars['route'].get())
        with patch('app.messagebox.askyesno', return_value=False):
            app.route_selection.set('Coding Plan 套餐')
            app.route_entry.event_generate('<<ComboboxSelected>>'); root.update()
        assert previous == (app.plan, app.form_signature(), app.revision, app.vars['route'].get())
        assert app.route_selection.get() == app.vars['route'].get()
        assert app.connection_state.get() == '文本请求已通过'
        app.choose_route()
        assert app.plan is previous[0]
        # Slow disk/history scan: callbacks return promptly, Tk continues and cancel is safe.
        config = fixture('async')
        app.vars['config'].set(str(config))
        app.tabs.select(4); wait_profiles(app)
        current = next(x for x in app.profile_choices if x['current'])
        for action in ('edit', 'preview', 'delete'):
            entered, release = threading.Event(), threading.Event()
            def slow(snap):
                entered.set()
                assert release.wait(5)
                return resolve_choices(snap)
            target = next(x for x in app.profile_choices if x['id'] not in ('account', current['id'])) if action == 'delete' else current
            with patch('profile_store.resolve_choices', side_effect=slow), patch('app.messagebox.askyesno') as ask:
                start = time.perf_counter()
                if action == 'edit': app.edit_profile(target['id'], str(config.resolve()))
                elif action == 'delete': app.delete_profile(target['id'], str(config.resolve()))
                else: app.make_preview()
                timings[action] = round((time.perf_counter() - start) * 1000, 2)
                assert timings[action] < 200, timings
                assert entered.wait(2)
                ticks = []
                root.after(0, lambda: ticks.append(True)); app.tabs.select(3); root.update()
                assert ticks and app.busy
                app.cancel_background(); release.set(); wait_profiles(app)
                ask.assert_not_called()
        # Backup page refreshes itself, filtering and restore state reflect eligibility.
        app.tabs.select(2); wait_profiles(app)
        assert app.backups
        app.backup_filter.set(True); app.render_backups()
        assert all(label.startswith('可恢复') for label in app.backup_list.get(0, 'end'))
        app.backup_filter.set(False); app.render_backups()
        stale = next(i for i, label in enumerate(app.backup_list.get(0, 'end')) if not label.startswith('可恢复'))
        app.backup_list.selection_set(stale); app.backup_selected()
        assert app.restore_button.instate(['disabled']) and '后续改动' in app.backup_state.get()
        app.show_error(ConfigError('HTTP 401：FAKE-SECRET https://private.example'))
        with patch.object(root, 'clipboard_clear'), patch.object(root, 'clipboard_append') as clipboard:
            app.copy_diagnostics()
            assert 'FAKE' not in clipboard.call_args.args[0] and 'private' not in clipboard.call_args.args[0]
        root.geometry('980x700'); root.update()
        out = ROOT / 'work/fix-0.10.13'; out.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(window=root.winfo_id()).save(out / 'backups.png')
        assert not callbacks, callbacks
        network.assert_not_called()
    root.destroy()
print('PASS: credentials, concurrent deletion, atomic load, route cancellation, async heartbeat/cancel, backups, sanitized diagnostics.', timings)
