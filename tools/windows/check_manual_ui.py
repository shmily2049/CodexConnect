from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
root_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir/'src'))
from app import App
with tempfile.TemporaryDirectory(dir=root_dir/'work') as tmp:
    config = Path(tmp)/'config.toml'
    window = tk.Tk()
    app = App(window, config, show_welcome=False)
    app.tabs.select(3)
    window.update()
    assert app.manual_button.winfo_ismapped()
    with patch('os.startfile') as launch:
        app.manual_button.invoke()
        manual = Path(launch.call_args.args[0])
        assert manual.read_bytes().startswith(b'%PDF-')
    with patch('sys._MEIPASS', tmp, create=True), patch('app.messagebox.showerror') as error:
        app.open_manual()
        error.assert_called_once()
    assert app.author_button.cget('image') and not app.author_button.cget('text')
    assert app.author_thumbnail.width()==144
    app.author_button.invoke()
    window.update()
    dialog=app.author_window
    assert dialog.winfo_exists() and dialog.title()=='二维码'
    assert dialog.qr_photo.width() in (215,430)
    app.author_button.invoke()
    assert app.author_window is dialog
    from PIL import ImageGrab
    ImageGrab.grab(window=dialog.winfo_id()).save(root_dir/'tools/windows/ui-author.png')
    dialog.destroy()
    assert not config.exists()
    window.destroy()
print('PASS: local PDF entry and missing-resource error; no config writes.')
