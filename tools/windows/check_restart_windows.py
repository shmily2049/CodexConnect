"""Exercise real WM_CLOSE and process observation on an owned dummy desktop app."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parents[1] / 'src'))
from desktop_restart import DesktopTarget, desktop_action, restart_desktop, _powershell

with tempfile.TemporaryDirectory(dir=base / 'test-temp') as scratch:
    folder = Path(scratch).resolve()
    assert folder.parent == (base / 'test-temp').resolve()
    source = folder / 'Fixture.cs'
    exe = folder / 'ChatGPT.exe'
    source.write_text('''using System;
using System.Windows.Forms;
class Fixture {
  [STAThread] static void Main() {
    var window = new Form();
    window.Text = "Codex Connect restart test - dummy window";
    window.Width = 400; window.Height = 160;
    Application.Run(window);
  }
}''')
    # Paths are from a controlled temporary directory, escaped as PS literals.
    quoted_source = str(source).replace("'", "''")
    quoted_exe = str(exe).replace("'", "''")
    _powershell("Add-Type -Path '" + quoted_source + "' -ReferencedAssemblies System.Windows.Forms,System.Drawing -OutputAssembly '" + quoted_exe + "' -OutputType WindowsApplication")
    target = DesktopTarget('win32', str(exe), 'owned dummy window')
    children = []
    def launch():
        child = subprocess.Popen([str(exe)])
        children.append(child)
        time.sleep(1)
    def action(target, operation):
        if operation == 'launch':
            launch()
            return ''
        return desktop_action(target, operation)
    try:
        launch()
        result = restart_desktop(target, action=action, timeout=10)
        assert len(children) == 2
        assert children[0].poll() == 0
        assert children[1].poll() is None
        print('PASS: real Windows graceful close, exit detection and new PID on owned dummy executable. Actual Codex untouched.')
    finally:
        desktop_action(target, 'quit')
        for child in children:
            child.wait(timeout=15)
