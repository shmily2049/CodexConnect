"""Offline concurrency, navigation and pagination regression for model reads."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch
from ui_test_support import wait_profiles
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from app import App
from profile_store import encode, state_path
from switch_profiles import choices, _choice
from desktop_ui import change_profile_page

with tempfile.TemporaryDirectory(prefix='async-profiles-') as temp:
    first = Path(temp) / 'one/config.toml'
    second = Path(temp) / 'two/config.toml'
    for config in (first, second):
        config.parent.mkdir()
        config.write_text('model="fixture"\n')
    items = [_choice(dict(model=f'model-{i}', model_provider='fixture',
                         model_providers={'fixture': dict(name='Fixture', base_url='https://example.com/v1')}))
             for i in range(40)]
    state_path(second).write_bytes(encode(set(), items))
    root = tk.Tk()
    app = App(root, first, show_welcome=False)
    failures = []
    root.report_callback_exception = lambda *args: failures.append(args)
    root.update()
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow_choices(snap, **kwargs):
        calls.append(str(snap.path))
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return choices(snap, **kwargs)
    with patch('app.choices', side_effect=slow_choices):
        start = time.perf_counter()
        app.tabs.select(4)
        assert time.perf_counter() - start < .2
        assert entered.wait(2)
        app.tabs.select(0)
        root.update()
        assert app.tabs.select() == 0 and app.profile_loading
        for _ in range(20):
            app.refresh_profiles()
        assert len(calls) == 1  # Coalesce reads; never launch an unbounded thread per click.
        app.vars['config'].set(str(second))
        app.tabs.select(4)
        release.set()
        wait_profiles(app)
        assert len(calls) == 2 and len(app.profile_choices) == 41
        assert app.profile_config_path == str(second.resolve())
    # Every model remains reachable, with at most six live cards per page.
    root.geometry('980x700')
    root.update()
    output = ROOT / 'work/fix-0.10.10'
    output.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(window=root.winfo_id()).save(output / 'model-pagination.png')
    seen = set()
    for page in range(7):
        assert app.profile_page == page and len(app.profile_cards) <= 6
        seen.update(app.profile_cards)
        if page < 6:
            change_profile_page(app, 1)
            root.update()
    assert seen == {item['id'] for item in app.profile_choices}
    assert app.profile_next.instate(['disabled'])
    second.write_text('[invalid')
    app.refresh_profiles()
    assert all(button.instate(['disabled']) for button in app.switch_buttons.values())
    wait_profiles(app)
    assert not app.profile_choices and not app.profile_cards
    assert '读取失败' in app.switch_state.get()
    second.write_text('model="recovered"\n')
    app.refresh_profiles()
    wait_profiles(app)
    assert len(app.profile_choices) == 41 and app.profile_page == 0
    # Closing a window during a slow read must not call Tk from its worker.
    gate = threading.Event()
    original_queue = app.profile_events
    def finishing_after_close(snap, **kwargs):
        assert gate.wait(5)
        return choices(snap, **kwargs)
    with patch('app.choices', side_effect=finishing_after_close):
        app.refresh_profiles()
        root.destroy()
        gate.set()
        original_queue.get(timeout=5)
    assert not failures, failures
print('PASS: nonblocking navigation, latest request wins, bounded worker, all 41 models paginated, stale/error clearing, recovery, close during read. No network.')
