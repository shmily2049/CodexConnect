import json
from pathlib import Path
import struct
import tarfile

ROOT = Path(__file__).resolve().parent

def inspect_macho(raw):
    if raw[:4] != b'\xcf\xfa\xed\xfe':
        return None
    _, cpu, subtype, kind, ncmd, size, flags, reserved = struct.unpack_from('<8I', raw)
    offset = 32
    deps, rpaths, minimum = [], [], None
    for _ in range(ncmd):
        cmd, length = struct.unpack_from('<II', raw, offset)
        if cmd in (0xC, 0x18, 0x80000018, 0x1F, 0x8000001F, 0x20, 0x80000020):
            name_offset = struct.unpack_from('<I', raw, offset + 8)[0]
            deps.append(raw[offset + name_offset:offset + length].split(b'\0')[0].decode())
        elif cmd == 0x8000001C:
            name_offset = struct.unpack_from('<I', raw, offset + 8)[0]
            rpaths.append(raw[offset + name_offset:offset + length].split(b'\0')[0].decode())
        elif cmd in (0x24, 0x32):
            minver = struct.unpack_from('<I', raw, offset + (8 if cmd == 0x24 else 12))[0]
            minimum = f'{minver >> 16}.{(minver >> 8) & 255}.{minver & 255}'
        offset += length
    return {'cpu': hex(cpu), 'minimum_macos': minimum, 'dependencies': deps, 'rpaths': rpaths}

if __name__ == '__main__':
    report = {}
    for filename in sorted(ROOT.glob('*apple-darwin-install_only.tar.gz')):
        with tarfile.open(filename) as archive:
            data = {}
            for item in archive:
                if item.isfile() and (item.name.endswith(('.dylib', '.so')) or item.name == 'python/bin/python3.12'):
                    meta = inspect_macho(archive.extractfile(item).read())
                    if meta:
                        data[item.name] = meta
            report[filename.name] = data
            print(filename.name, 'Mach-O files:',len(data))
            for name, meta in data.items():
                if any(k in name for k in ('bin/python3.12', '_tkinter', 'libtk', 'libtcl')):
                    print(name, meta)
    (ROOT / 'macho-report.json').write_text(json.dumps(report, indent=2))
