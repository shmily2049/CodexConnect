"""Opt-in graceful restart of the desktop client. Never terminates CLI processes."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
from provider_core import ConfigError, default_config


@dataclass(frozen=True)
class DesktopTarget:
    platform: str
    path: str
    label: str
    app_id: str = ''


def _run(args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout,
                                creationflags=0x08000000 if sys.platform == 'win32' else 0)
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigError('无法与桌面应用通信。请手动退出并重新打开 Codex。') from None
    if result.returncode:
        raise ConfigError('系统未完成桌面应用操作。请检查系统权限，或手动重启 Codex。')
    return result.stdout.strip()


def _powershell(script):
    # Scripts are fixed source; variable strings use JSON via environment data.
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return _run([str(executable), '-NoProfile', '-NonInteractive', '-Command', script])


WINDOWS_DISCOVERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$targets = @(Get-AppxPackage -Name OpenAI.Codex | ForEach-Object {
    $package = $_
    [xml]$manifest = Get-Content -LiteralPath (Join-Path $package.InstallLocation 'AppxManifest.xml')
    foreach ($application in $manifest.Package.Applications.Application) {
        $exe = Join-Path $package.InstallLocation $application.Executable
        if ((Split-Path $exe -Leaf) -in @('Codex.exe', 'ChatGPT.exe')) {
            [pscustomobject]@{path=$exe; label=(Split-Path $exe -Leaf); app_id=($package.PackageFamilyName + '!' + $application.Id)}
        }
    }
})
ConvertTo-Json -InputObject $targets -Compress
'''


def _win_script(target, action):
    # JSON encoded as base64 is data, never interpreted as PowerShell syntax.
    import base64
    data = base64.b64encode(json.dumps({'path': target.path, 'app_id': target.app_id}).encode()).decode()
    prefix = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
'''
    prefix += "$target = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + data + "')) | ConvertFrom-Json\n"
    prefix += "$matching = @(Get-Process -Name Codex,ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $target.path })\n"
    if action == 'running':
        return prefix + "if ($matching.Count -gt 0) { 'running' } else { 'stopped' }"
    if action == 'quit':
        return prefix + r'''
$windows = @($matching | Where-Object { $_.MainWindowHandle -ne 0 })
if ($matching.Count -gt 0 -and $windows.Count -eq 0) { throw 'No visible desktop window; exit from tray first.' }
foreach ($process in $windows) { if (-not $process.CloseMainWindow()) { throw 'Close request declined' } }
'''
    if action == 'launch':
        return prefix + r'''
if ($matching.Count -gt 0) { throw 'Desktop is still running' }
Start-Process -FilePath "$env:SystemRoot\explorer.exe" -ArgumentList ('shell:AppsFolder\' + $target.app_id) -WindowStyle Hidden
'''
    raise ValueError(action)


def _mac(target, action):
    bodies = {
        'running': 'return Application(argv[0]).running() ? "running" : "stopped";',
        'quit': 'var app = Application(argv[0]); if (app.running()) app.quit();',
    }
    if action == 'launch':
        return _run(['/usr/bin/open', '-a', target.path])
    return _run(['/usr/bin/osascript', '-l', 'JavaScript', '-e',
                 'function run(argv) { ' + bodies[action] + ' }', target.path])


def desktop_action(target, action):
    if target.platform == 'win32':
        return _powershell(_win_script(target, action))
    if target.platform == 'darwin':
        return _mac(target, action)
    raise ConfigError('自动重启目前支持 Windows 和 macOS 桌面版。')


def discover_desktop(config_path):
    if Path(config_path).expanduser().resolve() != default_config().resolve():
        raise ConfigError('当前选择的不是默认 Codex 配置文件。请取消自动重启，或先选择桌面版实际使用的配置文件。')
    if sys.platform == 'win32':
        try:
            entries = json.loads(_powershell(WINDOWS_DISCOVERY).lstrip('\ufeff'))
            if not isinstance(entries, list) or len(entries) != 1:
                raise ValueError()
            entry = entries[0]
            target = DesktopTarget('win32', entry['path'], entry['label'], entry['app_id'])
            if not Path(target.path).is_file():
                raise ValueError()
            return target
        except (ValueError, KeyError, TypeError):
            raise ConfigError('未能唯一识别 Microsoft Store 安装的 Codex 桌面版。请取消自动重启，改为手动重新打开。') from None
    if sys.platform == 'darwin':
        targets = []
        for directory in (Path('/Applications'), Path.home() / 'Applications'):
            for name in ('Codex.app', 'ChatGPT.app'):
                path = directory / name
                try:
                    info = plistlib.loads((path / 'Contents/Info.plist').read_bytes())
                    if str(info.get('CFBundleIdentifier', '')).startswith('com.openai.'):
                        targets.append(DesktopTarget('darwin', str(path), name))
                except (OSError, ValueError, plistlib.InvalidFileException):
                    continue
        running = [t for t in targets if desktop_action(t, 'running') == 'running']
        candidates = running or targets
        if len(candidates) == 1:
            return candidates[0]
        raise ConfigError('未能唯一识别 /Applications 或 ~/Applications 中的 Codex/ChatGPT 桌面版，请手动重启。')
    raise ConfigError('自动重启目前支持 Windows 和 macOS 桌面版。')


def restart_desktop(target, action=desktop_action, timeout=25, clock=time.monotonic, sleep=time.sleep):
    """Wait for a real exit before launch; no kill fallback, no config/auth access."""
    if action(target, 'running') == 'running':
        action(target, 'quit')
        deadline = clock() + timeout
        while action(target, 'running') == 'running':
            if clock() >= deadline:
                raise ConfigError('Codex 尚未完全退出（可能仍在托盘中或有退出提示）。没有强制结束进程，请手动退出后再点“重启 Codex”。')
            sleep(.5)
    action(target, 'launch')
    deadline = clock() + timeout
    while action(target, 'running') != 'running':
        if clock() >= deadline:
            raise ConfigError('已请求打开 Codex，但未检测到桌面进程。请从开始菜单或应用程序目录手动打开。')
        sleep(.5)
    return '已检测到桌面进程重新启动。请新建会话，确认所选模型；这不代表模型请求已验证。'
