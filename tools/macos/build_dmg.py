"""Build standard compressed UDIF/HFS+ DMGs and audit every stored entry in WSL."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[2]
if sys.platform=='win32':
    script='/mnt/'+ROOT.drive[0].lower()+ROOT.as_posix()[2:]+'/tools/macos/build_dmg.py'
    raise SystemExit(subprocess.call(['wsl','-d','Ubuntu-24.04','--','python3',script]))
sys.path.insert(0,str(ROOT/'src'))
from provider_core import VERSION
internal=ROOT/'work/build-artifacts'/VERSION
release=ROOT/'release'/('CodexConnect-'+VERSION)
release.mkdir(parents=True,exist_ok=True)
tools=ROOT/'work/linux-dmg'
helper=tools/'hfs_manifest'
dmg=tools/'build/dmg/dmg'
mkfs=tools/'deps/sbin/mkfs.hfsplus'
fsck=tools/'deps/sbin/fsck.hfsplus'
for tool in (helper,dmg,mkfs,fsck):
    assert tool.is_file(), 'Missing internal DMG build tool: '+str(tool)
results=[]
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
for chip in ('AppleSilicon','Intel'):
    filename=f'CodexConnect-{VERSION}-{chip}'
    source=internal/'mac-bundles'/(filename+'.zip')
    log=internal/(filename+'-dmg-build.log')
    with log.open('wb') as output, tempfile.TemporaryDirectory(prefix='codexconnect-dmg-') as tmp:
        temp=Path(tmp);stage=temp/'stage';stage.mkdir()
        entries={}
        with zipfile.ZipFile(source) as archive:
            assert archive.testzip() is None
            for info in archive.infolist():
                name=info.filename
                if '/' not in name:
                    name=f'CodexConnect-{VERSION}-UserGuide.pdf' if name.endswith('.pdf') else 'ReadMe.txt'
                rel=PurePosixPath(name)
                assert not rel.is_absolute() and '..' not in rel.parts and name.isascii() and '\t' not in name
                for parent in rel.parents:
                    if str(parent)!='.':entries.setdefault(str(parent),('D',0o40755,b''))
                data=archive.read(info)
                mode=info.external_attr>>16
                kind='L' if stat.S_ISLNK(mode) else 'F'
                assert kind=='L' or stat.S_ISREG(mode)
                if kind=='L':
                    target=data.decode();assert '\t' not in target and '\n' not in target and not target.startswith('/')
                    import posixpath
                    resolved=posixpath.normpath(posixpath.join(str(rel.parent),target))
                    assert resolved in archive.namelist() and resolved.startswith('CodexConnect.app/')
                entries[name]=(kind,mode,data)
        entries['Applications']=('L',0o120777,b'/Applications')
        ordered=sorted(entries,key=lambda name:(entries[name][0]!='D',len(PurePosixPath(name).parts),name))
        manifest=temp/'manifest.tsv'
        rows=[]
        for name in ordered:
            kind,mode,data=entries[name]
            path=stage/name
            if kind=='D':path.mkdir(parents=True,exist_ok=True)
            elif kind=='F':path.write_bytes(data)
            rows.append('\t'.join((kind,format(mode,'o'),name,data.decode() if kind=='L' else '-')))
        manifest.write_text('\n'.join(rows)+'\n')
        raw=temp/'image.hfs'
        with raw.open('wb') as stream:stream.truncate(max(256*1024**2,sum(len(e[2]) for e in entries.values())+64*1024**2))
        def run(args):subprocess.run([str(a) for a in args],check=True,stdout=output,stderr=subprocess.STDOUT)
        run([mkfs,'-v','CodexConnect-'+VERSION,raw])
        run([helper,'pack',raw,stage,manifest])
        run([fsck,'-n',raw])
        candidate=internal/(filename+'.dmg')
        run([dmg,'build',raw,candidate])
        with candidate.open('rb') as stream:
            stream.seek(-512,2);assert stream.read(4)==b'koly','Not a UDIF disk image'
        restored=temp/'restored.hfs'
        run([dmg,'extract',candidate,restored])
        assert sha(restored)==sha(raw),'DMG decompression differs from source HFS+'
        run([fsck,'-n',restored])
        audit=temp/'audit';audit.mkdir()
        for name in ordered:
            if entries[name][0]=='D':(audit/name).mkdir(parents=True,exist_ok=True)
        run([helper,'audit',restored,audit,manifest])
        for name,(kind,mode,data) in entries.items():
            if kind!='D':assert (audit/name).read_bytes()==data,name
        target=release/candidate.name
        import shutil
        shutil.copy2(candidate,target)
        result={'file':target.name,'sha256':sha(target),'zip_sha256':sha(source),'entries':len(entries),'files':sum(e[0]=='F' for e in entries.values()),'links':sum(e[0]=='L' for e in entries.values()),'permissions_verified':True,'fsck_passed':True,'udif_roundtrip_verified':True,'all_bytes_verified':True,'mac_runtime_tested':False,'signed':False,'notarized':False}
        results.append(result)
        print(json.dumps(result),flush=True)
(internal/'dmg-validation.json').write_text(json.dumps(results,indent=2))
