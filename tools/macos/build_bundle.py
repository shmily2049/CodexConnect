from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import plistlib
import posixpath
import stat
import tarfile
import zipfile
import argparse
import sys
from PIL import Image, ImageDraw

from inspect_runtime import inspect_macho

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
sys.path.insert(0, str(ROOT.parents[1] / 'src'))
from provider_core import VERSION
parser.add_argument('--output-dir', type=Path, default=ROOT.parents[1] / 'work/build-artifacts' / VERSION / 'mac-bundles')
OUT = parser.parse_args().output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT.parents[1] / 'src'
sys.path.insert(0, str(SOURCE))
from provider_core import VERSION
BUNDLE = 'CodexConnect.app'
RESOURCES = BUNDLE + '/Contents/Resources'
RUNTIME = RESOURCES + '/runtime/'
release = json.loads((ROOT / 'latest-release.json').read_bytes())
cert_source = json.loads((ROOT / 'certifi-source.json').read_bytes())


def add(z, name, data, mode=0o100644):
    info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
    info.create_system = 3
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data)


def launcher(arch):
    return f'''#!/bin/sh
set -eu
contents_dir="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
resources_dir="$contents_dir/Resources"
runtime_python="$resources_dir/runtime/python/bin/python3.12"
hardware="$(/usr/bin/uname -m)"
if [ "$hardware" != "{arch}" ]; then
  /usr/bin/osascript -e 'display alert "版本与芯片不匹配" message "请从关于本机确认芯片类型，并下载 Apple 芯片版或 Intel 版。无需安装 Python。" as critical'
  exit 1
fi
if [ ! -x "$runtime_python" ]; then
  /usr/bin/osascript -e 'display alert "应用不完整" message "请重新打开完整的 DMG，并将应用复制到“应用程序”后重试。" as critical'
  exit 1
fi
exec "$runtime_python" -I -B "$resources_dir/bootstrap.py" "$@"
'''.encode('utf-8')


def readme(label, minimum, archive_name, checksum):
    return f'''Codex 模型配置助手 {VERSION} macOS 内置运行时版

这个包适用于 {label}。
内置 Python 3.12.15、Tcl/Tk 9、TOML 解析库和 HTTPS CA 证书。
不需要安装 Python、Homebrew、pip 或命令行开发工具；启动不下载依赖。
运行时声明的最低系统要求为 macOS {minimum}。

使用方法
1. 双击打开 DMG 磁盘映像。
2. 将 CodexConnect.app 拖到“应用程序”，或在磁盘映像中直接打开。
3. 双击 CodexConnect.app，进入桌面配置界面。
4. 选择服务商、输入配置，检查预览，再确认保存。保存前自动备份原配置。
5. 完全退出并重新启动 Codex，在新会话中验证模型回复和工具调用。

第一次打开
此应用未使用 Apple Developer ID 签名，也未提交 Apple 公证。
因此不能保证第一次下载后直接双击即可放行。
如果 macOS 提示无法验证开发者，先确认来源和下面的完整性信息；
确认信任后，可以在“系统设置 → 隐私与安全性”中按系统提示打开此应用。
不需要关闭 Gatekeeper，也不需要执行移除整个目录安全属性的命令。
如果提示文件损坏、恶意软件或企业策略禁止运行，请不要绕过该提示。
若要面向其他用户正式发布并减少首次拦截，需要在 Mac 上完成 Developer ID 签名和公证。
Apple 官方说明：https://support.apple.com/en-hk/102445

配置说明
沿用 Windows 版功能：DeepSeek 预设、自定义 Responses 服务、脱敏预览、
模型目录读取与导入、备份恢复、可选短消息测试。
默认直接填写 API Key，保存时会确认密钥明文写入本机 config.toml。
已配置环境变量的用户可切换方式；Finder 启动的应用不一定继承终端中的变量。
服务标识自动生成，预览时自动处理重名，无需填写 Provider ID。
测试接口仅在你点击按钮并确认后发送一条短消息，可能产生少量费用。
没有自动扫描密钥、修改真实配置或执行第三方安装脚本的启动行为。
切换第三方 Provider 仍要求服务支持 Responses API。

验证范围
已完成运行时 SHA-256 核对、Mach-O 架构与动态库路径检查、
应用包结构和执行权限检查、Tcl/Tk 与证书文件检查。
测试记录按版本保存；Windows 回归、Mac 静态检查与真实服务验证分别记录。
Windows 检查不能代替 Mac 真机运行验证。完整记录见项目 docs/validation/，磁盘映像校验见 work/build-artifacts/{VERSION}/dmg-validation.json。
当前构建环境为 Windows，尚未在 Mac 真机上运行这个应用包。
此包提供“内置运行时、不另装 Python”的实现，不代表已完成 Mac 启动验收。

可选自检
在终端将应用拖入路径后，运行其内置启动器，例如：
  "/Applications/CodexConnect.app/Contents/MacOS/launch" --self-check
此命令只在临时目录构建界面、检查运行时和证书，不访问真实 Codex 配置。
成功后会输出 bundled_python、isolated 和 gui_constructed 为 true。

依赖来源与许可证
Python 来源：{release['release_url']}
运行时文件：{archive_name}
运行时 SHA-256：{checksum}
证书来源：certifi {cert_source['version']}，PyPI 官方发行文件。
应用内 Contents/Resources/THIRD_PARTY_LICENSES 保留运行时项目许可证；
其余依赖许可证随 runtime 和 app/vendor 一并保留。
源码位于应用内 Contents/Resources/app；用“显示包内容”可以查看。
'''.encode('utf-8')


icon_data = io.BytesIO((ROOT.parent / 'windows' / 'brand.icns').read_bytes())
bootstrap = (ROOT / 'bootstrap.py').read_bytes()
compile(bootstrap, 'bootstrap.py', 'exec')
results = []
for cpu, label, tag, minimum, machine in [
    ('aarch64', 'Apple 芯片 Mac', 'AppleSilicon', '11.0', 'arm64'),
    ('x86_64', 'Intel 芯片 Mac', 'Intel', '10.15', 'x86_64')]:
    archive_file = next(ROOT.glob(f'*{cpu}-apple-darwin-install_only.tar.gz'))
    checksum = (ROOT / (archive_file.name + '.sha256')).read_text().strip()
    assert hashlib.sha256(archive_file.read_bytes()).hexdigest() == checksum
    target = OUT / f'CodexConnect-{VERSION}-{tag}.zip'
    manifest = {'application': 'CodexConnect', 'version': VERSION, 'packaging_revision': 19,
                'architecture': machine, 'minimum_macos': minimum,
                'runtime': {'archive': archive_file.name, 'sha256': checksum, 'release': release},
                'certifi': cert_source, 'mac_runtime_tested': False, 'developer_id_signed': False,
                'notarized': False, 'source_sha256': {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                    for name in ('app.py', 'desktop_ui.py', 'desktop_widgets.py', 'app_icon.py', 'provider_core.py', 'switch_profiles.py', 'desktop_restart.py', 'provider_presets.py', 'beginner_help.py', 'profile_store.py', 'model_catalog.py')}}
    with tarfile.open(archive_file) as tar, zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        members = tar.getmembers()
        member_names = {m.name for m in members}
        for item in members:
            assert not item.name.startswith('/') and '..' not in PurePosixPath(item.name).parts
            if item.isdir():
                continue
            name = RUNTIME + item.name
            if item.issym():
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(item.name), item.linkname))
                assert resolved in member_names and resolved.startswith('python/')
                add(z, name, item.linkname.encode(), 0o120777)
            elif item.isfile() or item.islnk():
                data = tar.extractfile(item).read()
                add(z, name, data, 0o100000 | (item.mode & 0o777))
            else:
                raise RuntimeError('Unexpected runtime archive entry: ' + item.name)
        for path in SOURCE.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pyc', '.exe', '.cmd', '.command'):
                continue
            if path.name in ('使用说明.txt', '验证记录.txt'):
                continue
            add(z, RESOURCES + '/app/' + path.relative_to(SOURCE).as_posix(), path.read_bytes())
        info = {'CFBundleName': 'CodexConnect', 'CFBundleDisplayName': 'CodexConnect',
                'CFBundleExecutable': 'launch', 'CFBundleIdentifier': 'local.tools.codex-provider',
                'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': VERSION,
                'CFBundleVersion': '19', 'CFBundleInfoDictionaryVersion': '6.0',
                'CFBundleIconFile': 'AppIcon', 'LSMinimumSystemVersion': minimum,
                'LSArchitecturePriority': [machine], 'NSHighResolutionCapable': True,
                'NSRequiresAquaSystemAppearance': False}
        add(z, BUNDLE + '/Contents/Info.plist', plistlib.dumps(info))
        add(z, BUNDLE + '/Contents/PkgInfo', b'APPL????')
        add(z, BUNDLE + '/Contents/MacOS/launch', launcher(machine), 0o100755)
        add(z, RESOURCES + '/bootstrap.py', bootstrap)
        add(z, RESOURCES + '/AppIcon.icns', icon_data.getvalue())
        add(z, RESOURCES + '/build-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode())
        with zipfile.ZipFile(ROOT / 'certifi.whl') as cert:
            add(z, RESOURCES + '/certificates/cacert.pem', cert.read('certifi/cacert.pem'))
            license_name = next(n for n in cert.namelist() if n.endswith('/LICENSE'))
            add(z, RESOURCES + '/THIRD_PARTY_LICENSES/certifi-LICENSE', cert.read(license_name))
        with zipfile.ZipFile(ROOT / 'runtime-build-source.zip') as lic:
            for name in lic.namelist():
                if PurePosixPath(name).name.startswith('LICENSE'):
                    add(z, RESOURCES + '/THIRD_PARTY_LICENSES/' + PurePosixPath(name).name, lic.read(name))
        add(z, '请先阅读.txt', readme(label, minimum, archive_file.name, checksum))
        add(z, f'CodexConnect-{VERSION}-使用说明.pdf', (SOURCE / 'assets/manual.pdf').read_bytes())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        plist = plistlib.loads(z.read(BUNDLE + '/Contents/Info.plist'))
        assert plist['CFBundleExecutable'] == 'launch'
        for filename in (BUNDLE + '/Contents/MacOS/launch', RUNTIME + 'python/bin/python3.12'):
            assert (z.getinfo(filename).external_attr >> 16) & 0o111
        assert b' -I -B ' in z.read(BUNDLE + '/Contents/MacOS/launch')
        for filename in ('lib/tcl9.0/init.tcl', 'lib/tk9.0/tk.tcl', 'lib/python3.12/tkinter/__init__.py',
                         'lib/python3.12/lib-dynload/_tkinter.cpython-312-darwin.so', 'lib/python3.12/encodings/__init__.py'):
            assert RUNTIME + 'python/' + filename in z.namelist()
        meta = inspect_macho(z.read(RUNTIME + 'python/bin/python3.12'))
        assert meta['cpu'] == ('0x100000c' if cpu == 'aarch64' else '0x1000007')
        for name in manifest['source_sha256']:
            assert z.read(RESOURCES + '/app/' + name) == (SOURCE / name).read_bytes()
        assert z.read(RESOURCES + '/app/provider_core.py') == (SOURCE / 'provider_core.py').read_bytes()
    output_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    results.append({'file': target.name, 'sha256': output_sha, 'bytes': target.stat().st_size,
                    'architecture': machine, 'static_checks_passed': True, 'mac_runtime_tested': False})
    print(target.name, target.stat().st_size, output_sha, flush=True)
(ROOT / 'standalone-SHA256.txt').write_text(''.join(x['sha256'] + '  ' + x['file'] + '\n' for x in results))
(ROOT / 'bundle-validation.json').write_text(json.dumps(results, indent=2))
