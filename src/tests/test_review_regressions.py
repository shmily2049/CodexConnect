"""Review regressions using synthetic snapshots, mocked file reads and no desktop."""
import queue
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App
from provider_core import ConfigError, Settings, Snapshot, prepare, parse_config
from switch_profiles import choices


class ReviewRegressions(unittest.TestCase):
    def controller(self):
        return SimpleNamespace(events=queue.Queue(), busy=True, revision=2,
            testing_revision=1, fetch_button=Mock(), catalog_fetch_button=Mock(),
            test_button=Mock(), status=Mock(), connection_state=Mock(),
            show_error=Mock(), root=Mock(), poll=Mock(), poll_profiles=Mock())

    def test_old_request_failure_does_not_blame_new_configuration(self):
        app = self.controller()
        callback = Mock()
        app.events.put((callback, None, ConfigError('HTTP 401'), 1))
        App.poll(app)
        app.show_error.assert_not_called()
        app.connection_state.set.assert_not_called()
        callback.assert_not_called()
        self.assertFalse(app.busy)
        self.assertIsNone(app.testing_revision)
        app.test_button.configure.assert_called_once_with(state='normal')
        app.root.after.assert_called_once_with(100, app.poll)

    def test_old_success_is_not_applied(self):
        app = self.controller()
        callback = Mock()
        app.events.put((callback, 'old catalog', None, 1))
        App.poll(app)
        callback.assert_not_called()

    def test_current_request_failure_still_has_recovery(self):
        app = self.controller()
        app.testing_revision = 2
        error = ConfigError('HTTP 401')
        app.events.put((Mock(), None, error, 2))
        App.poll(app)
        app.show_error.assert_called_once_with(error)
        app.connection_state.set.assert_called_once_with('连接测试未通过')

    def test_restart_completion_survives_form_edits(self):
        app = self.controller()
        callback = Mock()
        app.events.put((callback, 'restarted', None, None))
        App.poll(app)
        callback.assert_called_once_with('restarted')

    def test_worker_captures_revision_before_form_edits(self):
        for track_changes in (True, False):
            app = self.controller()
            app.busy = False
            callback = Mock()
            with patch('app.threading.Thread') as thread:
                App.background(app, lambda: 'done', callback, 'working', track_changes)
                app.revision = 3
                thread.call_args.kwargs['target']()
            self.assertEqual(app.events.get_nowait(),
                             (callback, 'done', None, 2 if track_changes else None))

    def test_api_login_is_not_marked_as_chatgpt_account(self):
        snap = Snapshot(Path('fixture/config.toml').absolute(), True,
                        b'forced_login_method = "api"\n')
        with patch('switch_profiles.list_backups', return_value=[]):
            self.assertFalse(any(item['current'] for item in choices(snap)))

    def test_default_account_is_current(self):
        with patch('switch_profiles.list_backups', return_value=[]):
            items = choices(Snapshot(Path('fixture/config.toml').absolute(), False, b''))
        self.assertEqual([i['id'] for i in items if i['current']], ['account'])

    def test_changed_address_does_not_mark_old_service_current(self):
        # Backup metadata and bytes are synthetic; only current-vs-history selection is exercised.
        current = b'model="example"\nmodel_provider="custom"\n[model_providers.custom]\nbase_url="https://new.example/v1"\n'
        old = current.replace(b'new.example', b'old.example')
        snap = Snapshot(Path('fixture/config.toml').absolute(), True, current)
        backup = Mock()
        backup.is_symlink.return_value = False
        backup.__truediv__ = Mock()
        meta, raw = Mock(), Mock()
        backup.__truediv__.side_effect = [meta, raw]
        for file in (meta, raw):
            file.is_symlink.return_value = False
            file.stat.return_value = SimpleNamespace(st_size=100)
        import json
        from provider_core import digest
        meta.read_text.return_value = json.dumps(dict(version=1, config_path=str(snap.path),
            before_exists=True, before_sha256=digest(old)))
        raw.read_bytes.return_value = old
        with patch('switch_profiles.list_backups', return_value=[backup]):
            items = choices(snap)
        selected = [i for i in items if i['current']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['url'], 'https://new.example/v1')

    def test_catalog_relative_to_config_directory(self):
        snap = Snapshot(Path('fixture/config.toml').absolute(), False, b'')
        settings = Settings('custom', 'Example', 'example', 'https://example.com/v1',
                            catalog_path='catalog/models.json')
        expected = (snap.path.parent / 'catalog/models.json').resolve()
        with patch('profile_store.read_state', return_value=(None, set())), \
             patch('switch_profiles.list_backups', return_value=[]), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(Path, 'stat', return_value=SimpleNamespace(st_size=50)), \
             patch.object(Path, 'read_bytes', autospec=True,
                          return_value=b'{"models":[{"slug":"example"}]}') as read:
            plan = prepare(snap, settings)
        read.assert_called_once_with(expected)
        self.assertEqual(parse_config(plan.updated)['model_catalog_json'], plan.catalog_target.as_posix())
        self.assertNotEqual(plan.catalog_target, expected)

    def test_malformed_provider_has_controlled_error(self):
        for raw in (b'model_providers=1', b'[model_providers]\ncustom=1'):
            with self.assertRaises(ConfigError):
                prepare(Snapshot(Path('fixture/config.toml'), True, raw),
                        Settings('custom', 'Example', 'example', 'https://example.com/v1'))

    def test_editing_catalog_path_discards_downloaded_cache(self):
        app = SimpleNamespace(catalog_bytes=b'previous catalog')
        App.catalog_changed(app)
        self.assertIsNone(app.catalog_bytes)

    def test_downloaded_catalog_survives_its_display_update(self):
        app = SimpleNamespace(revision=1, catalog_bytes=None, vars={'catalog': Mock()},
                              status=Mock(), make_preview=Mock(), background=Mock())
        app.vars['catalog'].set.side_effect = lambda value: App.catalog_changed(app)
        App.fetch_catalog(app, continue_preview=True)
        data = b'{"models":[{"slug":"example"}]}'
        app.background.call_args.args[1](data)
        self.assertEqual(app.catalog_bytes, data)
        app.make_preview.assert_called_once_with()

    def test_save_and_restore_wait_for_background_operation(self):
        app = SimpleNamespace(busy=True, restart_running=False, status=Mock())
        with patch('app.apply_plan') as save, patch('app.restore_backup') as restore:
            App.save(app)
            App.restore(app)
            save.assert_not_called()
            restore.assert_not_called()

    def test_window_destroy_cancels_pending_poll(self):
        app = SimpleNamespace(root=Mock(), poll_after_id='pending')
        App.on_destroy(app, SimpleNamespace(widget=Mock()))
        app.root.after_cancel.assert_not_called()
        App.on_destroy(app, SimpleNamespace(widget=app.root))
        app.root.after_cancel.assert_called_once_with('pending')
        self.assertIsNone(app.poll_after_id)

    def test_manual_poll_does_not_duplicate_timer(self):
        app = self.controller()
        app.poll_after_id = 'previous'
        App.poll(app)
        app.root.after_cancel.assert_called_once_with('previous')
        self.assertEqual(app.poll_after_id, app.root.after.return_value)


if __name__ == '__main__':
    unittest.main()
