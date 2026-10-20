"""Offline regressions for coalesced painting and fresh configuration reads."""
from ui_test_support import wait_profiles
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from app import App
from provider_core import Settings, prepare, apply_plan, read_snapshot

with tempfile.TemporaryDirectory(prefix='ui-performance-') as temp:
    config = Path(temp) / 'config.toml'
    config.write_text('model="fixture"\n', encoding='utf-8')
    root = tk.Tk()
    failures = []
    root.report_callback_exception = lambda *args: failures.append(args)
    app = App(root, config, show_welcome=False)
    root.update()
    with patch.object(app, 'sync_summary', wraps=app.sync_summary) as summary:
        app.plan = object()
        revision = app.revision
        app.vars['name'].set('Fixture service')
        app.vars['model'].set('changed-model')
        app.vars['token'].set('FAKE-KEY')
        assert app.plan is None and app.revision > revision
        assert app.save_button.instate(['disabled'])
        assert summary.call_count == 0
        root.update()
        assert summary.call_count == 1
        assert app.summary_model.get() == 'changed-model'
    # A pending decorative update must never invalidate a newly prepared plan.
    app.vars['preset'].set('自定义 Responses 服务')
    app.preset_changed()
    app.vars['base_url'].set('https://example.com/v1')
    app.vars['model'].set('fixture-model')
    app.vars['token'].set('FAKE-KEY')
    app.make_preview();wait_profiles(app)
    plan = app.plan
    assert plan is not None
    root.update()
    assert app.plan is plan and app.save_button.instate(['!disabled'])
    for page in (0, 4, 3, 1, 5, 4):
        app.tabs.select(page);wait_profiles(app)
        root.update()
        assert [key for key, value in app.tabs.pages.items() if value[0].winfo_ismapped()] == [page]
    card = app.profile_cards['account']
    app.refresh_profiles();wait_profiles(app)
    assert app.profile_cards['account'] is card
    # External writes still appear immediately; render reuse never caches file contents.
    settings = Settings('fixture', 'Fixture', 'external-model', 'https://example.com/v1',
                        auth_mode='token', token='FAKE-KEY')
    apply_plan(prepare(read_snapshot(config), settings))
    app.refresh_profiles();wait_profiles(app)
    assert any(item['current'] and item['fields'].get('model') == 'external-model'
               for item in app.profile_choices)
    config.write_text('[broken', encoding='utf-8')
    with patch('app.messagebox.showerror'):
        app.refresh_profiles();wait_profiles(app)
    assert not app.profile_cards and '无法读取' in app.selected_model.get()
    app.vars['model'].set('pending-on-close')
    root.destroy()
    assert app.summary_after_id is None and app.poll_after_id is None
    assert not failures, failures
print('PASS: immediate invalidation, one summary per event burst, valid preview survives, hidden pages unmapped, fresh external changes, stale cards cleared, clean shutdown. No network.')
