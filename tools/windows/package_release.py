"""Publish one directly runnable Windows EXE; keep build metadata internal."""
from pathlib import Path
import argparse
import hashlib
import shutil
import sys
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'src'))
from provider_core import VERSION
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, default=root / 'release' / ('CodexConnect-' + VERSION))
parser.add_argument('--skip-preview', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--input-exe', type=Path, default=root / 'tools/windows/dist/CodexConnect.exe')
args = parser.parse_args()
output = args.output_dir.resolve()
output.mkdir(parents=True, exist_ok=True)
exe = output / f'CodexConnect-{VERSION}.exe'
shutil.copy2(args.input_exe.resolve(), exe)
shutil.copy2(root / 'src/assets/manual.pdf', output / f'CodexConnect-{VERSION}-使用说明.pdf')
internal = root / 'work/build-artifacts' / VERSION
internal.mkdir(parents=True, exist_ok=True)
(internal / 'Windows-SHA256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest() + '  ' + exe.name + '\n', encoding='utf-8')
print(exe.name, exe.stat().st_size)
