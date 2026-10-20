from pathlib import Path
import json
import posixpath
import ssl
import stat
import zipfile
import argparse
from inspect_runtime import inspect_macho

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
import sys
sys.path.insert(0, str(ROOT.parents[1] / 'src'))
from provider_core import VERSION
parser.add_argument('--output-dir', type=Path, default=ROOT.parents[1] / 'work/build-artifacts' / VERSION / 'mac-bundles')
OUT = parser.parse_args().output_dir.resolve()
PREFIX = 'CodexConnect.app/Contents/Resources/runtime/'
records = []
for filename in sorted(OUT.glob(f'CodexConnect-{VERSION}-*.zip')):
    with zipfile.ZipFile(filename) as z:
        names = set(z.namelist())
        executable = PREFIX + 'python/bin/python3.12'
        exe_dir = posixpath.dirname(executable)
        macho_count = 0
        dependency_count = 0
        symlink_count = 0
        for item in z.infolist():
            assert not item.filename.startswith('/') and '..' not in Path(item.filename).parts
            if stat.S_ISLNK(item.external_attr >> 16):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(item.filename), z.read(item).decode()))
                assert target in names and target.startswith(PREFIX)
                symlink_count += 1
            if item.filename == executable or item.filename.endswith(('.so', '.dylib')):
                meta = inspect_macho(z.read(item))
                if not meta:
                    continue
                macho_count += 1
                for dep in meta['dependencies']:
                    dependency_count += 1
                    if dep.startswith(('/usr/lib/', '/System/Library/')):
                        continue
                    def expand(value):
                        return posixpath.normpath(value.replace('@loader_path', posixpath.dirname(item.filename)).replace('@executable_path', exe_dir))
                    if dep.startswith('@rpath/'):
                        candidates = [expand(rpath + '/' + dep[len('@rpath/'):]) for rpath in meta['rpaths']]
                        candidates.append(expand('@executable_path/../lib/' + dep[len('@rpath/'):]))
                    else:
                        candidates = [expand(dep)]
                    assert any(p in names for p in candidates), (item.filename, dep, candidates)
        pem = z.read('CodexConnect.app/Contents/Resources/certificates/cacert.pem').decode('ascii')
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cadata=pem)
        assert len(ctx.get_ca_certs()) > 100
        manifest = json.loads(z.read('CodexConnect.app/Contents/Resources/build-manifest.json'))
        assert not manifest['notarized'] and not manifest['mac_runtime_tested']
        records.append({'bundle': filename.name, 'macho_files': macho_count,
                        'resolved_or_system_dependencies': dependency_count, 'valid_symlinks': symlink_count,
                        'ca_certificates': len(ctx.get_ca_certs()), 'passed': True})
        print(records[-1])
assert records, 'No standalone macOS bundles found in the selected output directory.'
(ROOT / 'dependency-validation.json').write_text(json.dumps(records, indent=2))
