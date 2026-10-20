"""Real Tk event-loop checks using only isolated config and blocked mock work."""
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
from provider_core import Settings, prepare, apply_plan, read_snapshot
from switch_profiles import choices, prepare_switch_review

with tempfile.TemporaryDirectory() as scratch:
    config = Path(scratch) / 'config.toml'
    config.write_text('model="account"\n')
    apply_plan(prepare(read_snapshot(config), Settings('fixture', 'Fixture', 'old-model',
        'https://example.com/v1', auth_mode='token', token='FAKE-KEY')))
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    failures = []
    root.report_callback_exception = lambda *args: failures.append(args)
    with patch('app.messagebox.showinfo'), patch('app.messagebox.showerror') as errors:
        app.tabs.select(4); wait_profiles(app)
        old = next(x for x in app.profile_choices if x['current'])
        app.edit_profile(old['id'], str(config.resolve()));wait_profiles(app)
        assert app.model_heading.get() == '编辑模型'
        app.vars['model'].set('unsaved')
        with patch('app.messagebox.askyesno', return_value=False):
            app.tabs.buttons[0].invoke()
        assert app.editing_profile and app.vars['model'].get() == 'unsaved'
        with patch('app.messagebox.askyesno', return_value=True):
            app.tabs.buttons[0].invoke()
            assert app.editing_profile is None and app.model_heading.get() == '添加模型'
            app.vars['name'].set('New')
            app.vars['model'].set('new-model')
            app.vars['base_url'].set('https://example.com/v1')
            app.vars['token'].set('FAKE-KEY')
            app.make_preview();wait_profiles(app); app.save();wait_profiles(app)
        assert any(x['id'] == old['id'] for x in choices(read_snapshot(config)))
        app.tabs.select(4); wait_profiles(app)
        current = app.selected_model.get()
        with patch('app.read_snapshot', side_effect=AssertionError('Search must not read disk')):
            app.profile_search.set('OLD-MODEL'); root.update()
            assert set(app.profile_cards) == {old['id']}
            assert app.selected_model.get() == current
            app.profile_search.set('no-such-model'); root.update()
            assert not app.profile_cards
            app.profile_search.set(''); root.update()
            assert len(app.profile_cards) == 3
        before = config.read_bytes()
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return prepare_switch_review(*args, **kwargs)
        with patch('switch_profiles.prepare_switch_review', side_effect=slow), patch('app.messagebox.askyesno', return_value=False) as ask:
            start = time.perf_counter()
            app.switch_profile('account', str(config.resolve()))
            elapsed = (time.perf_counter() - start) * 1000
            assert elapsed < 200
            assert entered.wait(2)
            ticks = []
            root.after(0, lambda: ticks.append(True))
            app.tabs.select(3); root.update()
            assert ticks and app.busy and app.tabs.select() == 3
            release.set(); wait_profiles(app)
            ask.assert_called_once()
            assert config.read_bytes() == before
        # A form change while preparation runs invalidates its pending confirmation.
        entered.clear(); release.clear()
        with patch('switch_profiles.prepare_switch_review', side_effect=slow), patch('app.messagebox.askyesno') as ask:
            app.switch_profile('account', str(config.resolve()))
            assert entered.wait(2)
            app.vars['model'].set('changed-during-preparation')
            release.set(); wait_profiles(app)
            ask.assert_not_called()
            assert config.read_bytes() == before
        # A corrupt entry coexists with healthy backups; it cannot reach confirmation.
        bad = config.parent / 'provider-tool-backups/20261019-000000-bad'
        bad.mkdir(); (bad / 'manifest.json').write_text('[]')
        app.refresh_backups();wait_profiles(app)
        labels = app.backup_list.get(0, 'end')
        assert any('备份损坏' in value for value in labels)
        assert any('可恢复' in value for value in labels)
        app.backup_list.selection_clear(0, 'end')
        app.backup_list.selection_set(app.backups.index(bad))
        with patch('app.messagebox.askyesno') as ask:
            app.restore(); ask.assert_not_called()
        assert errors.call_count == 1
        app.vars['model'].set('new-model')
        app.tabs.select(4); wait_profiles(app)
        assert 'new-model' in app.selected_model.get()
        root.geometry('980x700'); root.update()
        out = ROOT / 'work/fix-0.10.11'
        out.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(window=root.winfo_id()).save(out / 'models-search.png')
        assert not failures, failures
    root.destroy()
print(f'PASS: same-page add/edit, search without I/O, async switch returned in {elapsed:.2f} ms, Tk heartbeat, cancellation, stale result, malformed backup isolation.')
