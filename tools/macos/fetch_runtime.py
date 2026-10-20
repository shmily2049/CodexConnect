from pathlib import Path
import hashlib
from html.parser import HTMLParser
import json
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(v for k, v in attrs if k == 'href')

meta = json.loads((ROOT / 'latest-release.json').read_bytes())
url = 'https://github.com/astral-sh/python-build-standalone/releases/expanded_assets/' + meta['tag']
html = urllib.request.urlopen(url, timeout=30).read()
(ROOT / 'assets.html').write_bytes(html)
parser = Links()
parser.feed(html.decode())
matches = [link for link in parser.links if 'cpython-3.12.' in link and 'apple-darwin-install_only.tar.gz' in link and not link.endswith('.sha256')]
print('Available runtime archives:', matches, flush=True)
sum_data = urllib.request.urlopen(meta['asset_url_prefix'] + '/SHA256SUMS', timeout=30).read()
(ROOT / 'SHA256SUMS').write_bytes(sum_data)
checksums = {line.split()[1].lstrip('*'): line.split()[0] for line in sum_data.decode().splitlines() if line.strip()}
for link in matches:
    download = 'https://github.com' + link if link.startswith('/') else link
    name = download.rsplit('/', 1)[-1]
    dest = ROOT / name
    checksum = checksums[name]
    if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != checksum:
        print('Downloading', name, flush=True)
        with urllib.request.urlopen(download, timeout=60) as response, dest.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == checksum
    with tarfile.open(dest) as archive:
        members = archive.getmembers()
        paths = [m.name for m in members]
        print('Verified', name, 'bytes', dest.stat().st_size, 'sha256', checksum, flush=True)
        print('Tcl/Tk:', [p for p in paths if p.endswith(('init.tcl', 'tk.tcl')) or '_tkinter' in p][:12], flush=True)
        print('Python binaries:', [p for p in paths if '/bin/python' in p], flush=True)
        print('Metadata:', [p for p in paths if 'PYTHON.json' in p or 'LICENSE' in p][:10], flush=True)
    (ROOT / (name + '.sha256')).write_text(checksum + '\n')
