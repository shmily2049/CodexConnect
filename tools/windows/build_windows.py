import os
import argparse
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
source = root.parents[1] / 'src'
parser = argparse.ArgumentParser()
parser.add_argument('--dist-dir', type=Path, default=root / 'dist')
args = parser.parse_args()
sys.path.insert(0, str(root / 'packages'))
os.environ['PYINSTALLER_CONFIG_DIR'] = str(root / 'pyinstaller-cache')
from PyInstaller.__main__ import run
run(['--clean', '--onefile', '--windowed', '--noconfirm', '--name', 'CodexConnect', '--icon', str(root / 'brand.ico'),
     '--add-data', str(source / 'assets') + ';assets',
     '--paths', str(source / 'vendor'), '--distpath', str(args.dist_dir.resolve()),
     '--workpath', str(root / 'build'), '--specpath', str(root), str(source / 'app.py')])
