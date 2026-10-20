"""Recovery guidance must remain actionable without exposing server text or keys."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beginner_help import explain_error, key_help
from provider_core import ConfigError
from provider_presets import PRESETS, get_preset
from unittest.mock import Mock
from types import SimpleNamespace


class BeginnerHelpTests(unittest.TestCase):
    def test_http_recovery_and_no_raw_body(self):
        for code,action in ((401,'key'),(403,'help'),(404,'model'),(429,'help'),(500,'')):
            result=explain_error(ConfigError(f'HTTP {code}：FAKE-PRIVATE-SERVER-TEXT'))
            self.assertEqual(result.action,action)
            self.assertNotIn('FAKE-PRIVATE',result.message)
            self.assertNotIn('HTTP',result.title)

    def test_sensitive_unknown_exceptions_are_never_displayed(self):
        for err in (ValueError('SECRET'),ConfigError('SECRET'),PermissionError('SECRET')):
            result=explain_error(err)
            self.assertNotIn('SECRET',result.message)

    def test_file_and_catalog_recovery_do_not_ask_users_to_edit_code(self):
        for message, action in (
            ('配置不是有效的 UTF-8 TOML','settings'),
            ('官方页面结构或模型目录已变化','catalog'),
            ('配置已被其他程序修改','preview'),
            ('需要检查 .provider-tool.lock 锁文件',''),
            ('备份校验失败','backups'),
            ('当前没有可载入的自定义 Provider','welcome'),
        ):
            result=explain_error(ConfigError(message))
            self.assertEqual(result.action,action)
            for technical in ('TOML','JSON','.lock','slug'):
                self.assertNotIn(technical,result.message)

    def test_guides_match_provider_and_route(self):
        for preset in PRESETS:
            for route in preset.routes:
                title,body=key_help(preset,route)
                self.assertIn('测试可能产生少量费用',body)
                if preset.docs:
                    self.assertIn(preset.credential,body)
                    self.assertIn(route.label,body)
                else:
                    self.assertIn('Responses',body)
        title,body=key_help(get_preset('Claude · OpenRouter'),get_preset('Claude · OpenRouter').routes[0])
        self.assertIn('OpenRouter',title)
        self.assertIn('不要填 Anthropic',body)

    def test_welcome_can_continue_when_preferences_are_read_only(self):
        from app import App
        marker=Mock()
        marker.parent.mkdir.side_effect=PermissionError('PRIVATE-PATH')
        fake=SimpleNamespace(welcome_marker=marker,tabs=Mock(),status=Mock())
        App.finish_welcome(fake,0)
        fake.tabs.select.assert_called_once_with(0)
        self.assertNotIn('PRIVATE-PATH',fake.status.set.call_args.args[0])


if __name__=='__main__':unittest.main()
