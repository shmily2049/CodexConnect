"""Windows-only release checks. Uses temporary config; never calls model APIs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools/windows/packages'))
from provider_core import VERSION
from PyInstaller.archive.readers import CArchiveReader


def strings(code):
    for value in code.co_consts:
        if isinstance(value, str):
            yield value
        elif isinstance(value, types.CodeType):
            yield from strings(value)


def main():
    release = ROOT / 'release' / ('CodexConnect-' + VERSION)
    exe = release / f'CodexConnect-{VERSION}.exe'
    out = ROOT / 'work/build-artifacts' / VERSION
    results = []

    def check(name, operation):
        try:
            operation()
            results.append(dict(name=name, passed=True))
        except Exception as error:
            results.append(dict(name=name, passed=False, error=str(error)))
        print(name, 'PASS' if results[-1]['passed'] else 'FAIL', flush=True)

    def integrity():
        archive = CArchiveReader(str(exe))
        for name in ('manual.pdf', 'author-qr.png', 'codex-fallback-template.json', 'codex-bundled-models.json', 'codex-LICENSE.txt', 'codex-catalog-NOTICE.txt'):
            key = next(k for k in archive.toc if k.replace('\\', '/') == 'assets/' + name)
            assert archive.extract(key) == (ROOT / 'src/assets' / name).read_bytes(), name
        assert (release / f'CodexConnect-{VERSION}-使用说明.pdf').read_bytes() == (ROOT / 'src/assets/manual.pdf').read_bytes()
        pyz = archive.open_embedded_archive(next(k for k in archive.toc if k.endswith('.pyz')))
        assert 'model_catalog' in pyz.toc and 'profile_store' in pyz.toc
        assert VERSION in set(strings(pyz.extract('provider_core')))
        for module in ('desktop_ui', 'switch_profiles', 'provider_presets'):
            text = '\n'.join(strings(pyz.extract(module)))
            assert 'ChatGPT套餐' in text, module
            assert 'GPT套餐' not in text.replace('ChatGPT套餐', ''), module
        expected = (out / 'Windows-SHA256.txt').read_text().split()[0]
        assert hashlib.sha256(exe.read_bytes()).hexdigest() == expected

    with tempfile.TemporaryDirectory(prefix='windows-check-', dir=ROOT / 'work') as temp:
        scratch = Path(temp)
        env = os.environ.copy()
        for key in list(env):
            if key.upper() in ('PYTHONHOME', 'PYTHONPATH', 'PATH', 'CODEX_HOME'):
                env.pop(key)
        env['PATH'] = str(Path(os.environ['SYSTEMROOT']) / 'System32')
        env['CODEX_HOME'] = str(scratch / 'unused-config')
        def run(name, command, cwd=ROOT):
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=60)
            log = result.stdout + result.stderr
            (out / (name + '.log')).write_bytes(log)
            assert result.returncode == 0, result.returncode
            assert not any(s in log for s in (b'Traceback', b'Exception in Tkinter callback'))
        check('embedded-assets-version-labels-sha256', integrity)
        check('standalone-smoke', lambda: run('standalone-smoke', [str(exe), '--smoke-ui']))
        folder = scratch / '中文路径 with spaces'
        folder.mkdir()
        portable = folder / exe.name
        portable.write_bytes(exe.read_bytes())
        check('unicode-path-no-python', lambda: run('unicode-path-no-python', [str(portable), '--smoke-ui'], folder))
        check('root-launcher-smoke', lambda: run('root-launcher-smoke', [os.environ['COMSPEC'], '/d', '/c', str(ROOT / '启动应用.cmd'), '--smoke-ui']))
        check('isolated-home-unchanged', lambda: unchanged(scratch / 'unused-config'))
    (out / 'windows-release-tests.json').write_text(json.dumps(dict(version=VERSION, scope='Windows only; no real config or API', results=results), ensure_ascii=False, indent=2), encoding='utf-8')
    return int(any(not item['passed'] for item in results))


def unchanged(path):
    assert not path.exists(), 'Unexpected config access created a home directory'


if __name__ == '__main__':
    raise SystemExit(main())
