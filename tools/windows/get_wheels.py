import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT.parents[1] / 'src' / 'vendor'
packages = [('tomlkit', '0.13.3', VENDOR), ('pyinstaller', '6.16.0', ROOT / 'packages'),
            ('altgraph', '0.17.4', ROOT / 'packages'), ('pefile', '2023.2.7', ROOT / 'packages'),
            ('pywin32-ctypes', '0.2.3', ROOT / 'packages'),
            ('pyinstaller-hooks-contrib', '2025.9', ROOT / 'packages'),
            ('packaging', '25.0', ROOT / 'packages'), ('setuptools', '80.9.0', ROOT / 'packages')]
for name, version, dest in packages:
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=20) as res:
        info = json.load(res)
    wheels = [u for u in info['urls'] if u['filename'].endswith('.whl') and ('none-any' in u['filename'] or 'win_amd64' in u['filename'])]
    assert len(wheels) == 1, (name, [u['filename'] for u in wheels])
    item = wheels[0]
    with urllib.request.urlopen(item['url'], timeout=30) as res:
        content = res.read()
    assert hashlib.sha256(content).hexdigest() == item['digests']['sha256']
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for member in z.infolist():
            path = (dest / member.filename).resolve()
            assert path.is_relative_to(dest.resolve())
        z.extractall(dest)
    print('Verified and extracted', item['filename'], flush=True)
