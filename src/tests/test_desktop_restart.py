import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
from desktop_restart import DesktopTarget, restart_desktop, discover_desktop, _win_script, ConfigError


class RestartTests(unittest.TestCase):
    target = DesktopTarget('win32', r'C:\Program Files\Codex\ChatGPT.exe', 'ChatGPT.exe', 'OpenAI.Codex_test!App')

    def test_restart_waits_for_exit_then_checks_start(self):
        states = iter(['running', 'running', 'stopped', 'stopped', 'running'])
        calls = []
        def action(target, op):
            calls.append(op)
            if op == 'running':
                return next(states)
        result = restart_desktop(self.target, action=action, sleep=lambda _: None)
        self.assertEqual(calls, ['running', 'quit', 'running', 'running', 'launch', 'running', 'running'])
        self.assertIn('重新启动', result)

    def test_declined_quit_never_launches(self):
        calls = []
        now = [0]
        def action(target, op):
            calls.append(op)
            return 'running'
        def sleep(seconds):
            now[0] += seconds
        with self.assertRaisesRegex(ConfigError, '没有强制'):
            restart_desktop(self.target, action=action, timeout=1, clock=lambda:now[0], sleep=sleep)
        self.assertNotIn('launch', calls)

    def test_stopped_app_is_opened_without_quit(self):
        calls = []
        def action(target, op):
            calls.append(op)
            if op == 'running':
                return 'running' if 'launch' in calls else 'stopped'
        restart_desktop(self.target, action=action)
        self.assertEqual(calls, ['running', 'launch', 'running'])

    def test_failure_to_open_is_not_reported_as_success(self):
        now = [0]
        def sleep(seconds):
            now[0] += seconds
        with self.assertRaisesRegex(ConfigError, '未检测到'):
            restart_desktop(self.target, action=lambda *args:'stopped', timeout=1,
                            clock=lambda:now[0], sleep=sleep)

    def test_request_error_never_launches(self):
        calls = []
        def action(target, op):
            calls.append(op)
            if op == 'quit':
                raise ConfigError('rejected')
            return 'running'
        with self.assertRaises(ConfigError):
            restart_desktop(self.target, action=action)
        self.assertEqual(calls, ['running', 'quit'])

    def test_custom_config_rejected_before_discovery(self):
        with patch('desktop_restart.default_config', return_value=Path('default/config.toml')), patch('desktop_restart._powershell') as command:
            with self.assertRaises(ConfigError):
                discover_desktop('another/config.toml')
            command.assert_not_called()

    def test_windows_commands_pin_executable_and_do_not_force_kill(self):
        for operation in ('quit', 'running', 'launch'):
            script = _win_script(self.target, operation)
            self.assertIn('$_.Path -eq $target.path', script)
            self.assertNotIn('Stop-Process', script)
            self.assertNotIn('taskkill', script)
        self.assertIn('CloseMainWindow', _win_script(self.target, 'quit'))

    def test_windows_target_strings_are_not_shell_code(self):
        target = DesktopTarget('win32', 'C:\\foo`$(bad)\\ChatGPT.exe', 'Codex', 'value;bad')
        script = _win_script(target, 'quit')
        self.assertNotIn('$(bad)', script)
        self.assertNotIn('value;bad', script)


if __name__ == '__main__':
    unittest.main()
