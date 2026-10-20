"""Validate versioned applications and standalone PDF; store checksums internally."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tools/windows/packages'))
from provider_core import VERSION
from PyInstaller.archive.readers import CArchiveReader
release=ROOT/'release'/('CodexConnect-'+VERSION)
internal=ROOT/'work/build-artifacts'/VERSION
internal.mkdir(parents=True,exist_ok=True)
expected={f'CodexConnect-{VERSION}.exe',f'CodexConnect-{VERSION}-AppleSilicon.dmg',f'CodexConnect-{VERSION}-Intel.dmg',f'CodexConnect-{VERSION}-使用说明.pdf'}
import shutil
shutil.copy2(ROOT/'src/assets/manual.pdf',release/f'CodexConnect-{VERSION}-使用说明.pdf')
assert {p.name for p in release.iterdir()}==expected
manual=(ROOT/'src/assets/manual.pdf').read_bytes()
assert manual.startswith(b'%PDF-')
exe=CArchiveReader(str(release/f'CodexConnect-{VERSION}.exe'))
key=next(k for k in exe.toc if k.replace('\\','/')=='assets/manual.pdf')
assert exe.extract(key)==manual
qr=(ROOT/'src/assets/author-qr.png').read_bytes()
qr_key=next(k for k in exe.toc if k.replace('\\','/')=='assets/author-qr.png')
assert exe.extract(qr_key)==qr
reports=json.loads((internal/'dmg-validation.json').read_text())
assert len(reports)==2
for item in reports:
 assert hashlib.sha256((release/item['file']).read_bytes()).hexdigest()==item['sha256']
 assert item['permissions_verified'] and item['fsck_passed'] and item['udif_roundtrip_verified'] and item['all_bytes_verified']
 source=internal/'mac-bundles'/item['file'].replace('.dmg','.zip')
 assert hashlib.sha256(source.read_bytes()).hexdigest()==item['zip_sha256']
for p in (internal/'mac-bundles').glob('*.zip'):
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  assert z.read(f'CodexConnect-{VERSION}-使用说明.pdf')==manual
  assert z.read('CodexConnect.app/Contents/Resources/app/assets/manual.pdf')==manual
  assert z.read('CodexConnect.app/Contents/Resources/app/assets/author-qr.png')==qr
  assert z.read('CodexConnect.app/Contents/Resources/app/app.py')==(ROOT/'src/app.py').read_bytes()
manifest=''.join(hashlib.sha256((release/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in sorted(expected))
(internal/'ALL-SHA256.txt').write_text(manifest,encoding='utf-8')
print('PASS: three applications plus PDF, matching embedded PDF/QR assets and verified DMG images; checksums internal.')
