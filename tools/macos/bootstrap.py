"""Starts the bundled desktop tool without using system Python or site packages."""
from pathlib import Path
import json
import os
import subprocess
import sys

resources = Path(__file__).resolve().parent
runtime = resources / 'runtime' / 'python'
os.environ['TCL_LIBRARY'] = str(runtime / 'lib' / 'tcl9.0')
os.environ['TK_LIBRARY'] = str(runtime / 'lib' / 'tk9.0')
os.environ['SSL_CERT_FILE'] = str(resources / 'certificates' / 'cacert.pem')
sys.path.insert(0, str(resources / 'app'))
sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if not arg.startswith('-psn_')]


def main():
    if '--self-check' in sys.argv:
        import ssl
        import tkinter as tk
        import tempfile
        from app import App
        with tempfile.TemporaryDirectory(prefix='codex-provider-selfcheck-') as scratch:
            root = tk.Tk()
            root.withdraw()
            app = App(root, Path(scratch) / 'config.toml')
            root.update_idletasks()
            result = {'python': sys.version.split()[0], 'tk': root.tk.call('package', 'require', 'Tk'),
                      'certificate_count': len(ssl.create_default_context().get_ca_certs()),
                      'bundled_python': str(sys.executable).startswith(str(runtime)),
                      'isolated': bool(sys.flags.isolated), 'gui_constructed': True,
                      'real_config_accessed': False}
            root.destroy()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    from app import main as run_app
    run_app()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Do not put exceptions, local settings, or credentials in persistent logs.
        if '--self-check' in sys.argv:
            import traceback
            traceback.print_exc()
        else:
            subprocess.run(['/usr/bin/osascript', '-e',
                'display alert "配置助手未能启动" message "请确认下载的版本与 Mac 芯片匹配，并完整解压应用。此版本尚未完成 Mac 真机验收；可使用随附说明中的自检命令获取启动信息。" as critical'],
                check=False, capture_output=True)
        sys.exit(1)
