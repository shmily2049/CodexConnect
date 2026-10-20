"""Offline model-list benchmark with realistic legacy history and many choices."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from app import App

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='models-benchmark-') as temp:
    config = Path(temp) / 'config.toml'
    config.write_text('model="fixture-account"\n', encoding='utf-8')
    backups = config.parent / 'provider-tool-backups'
    for index in range(120):
        directory = backups / f'20261019-120000-{index:08d}'
        directory.mkdir(parents=True)
        raw = (f'model="fixture-{index % 40}"\nmodel_provider="fixture"\n'
               '[model_providers.fixture]\nname="Fixture"\nbase_url="https://example.com/v1"\n'
               'wire_api="responses"\nrequires_openai_auth=false\n'
               'experimental_bearer_token="FAKE-KEY"\n'
               '[projects]\n' + ''.join(f'"fixture-{n}"={{trust_level="trusted"}}\n' for n in range(120))).encode()
        (directory / 'original.config.toml').write_bytes(raw)
        (directory / 'manifest.json').write_text(json.dumps(dict(
            version=1, config_path=str(config.resolve()), before_exists=True,
            before_sha256=hashlib.sha256(raw).hexdigest())))
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    root.update()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    gaps = []
    last_tick = time.perf_counter()
    def heartbeat():
        global last_tick
        now = time.perf_counter()
        gaps.append((now - last_tick) * 1000)
        last_tick = now
        root.after(10, heartbeat)
    tick = root.after(10, heartbeat)
    records = []
    for _ in range(2):
        app.tabs.select(0)
        root.update()
        start = time.perf_counter()
        app.tabs.select(4)
        returned = time.perf_counter()
        deadline = start + 30
        while getattr(app, 'profile_loading', False):
            root.update()
            assert time.perf_counter() < deadline, 'Model loading timed out'
            time.sleep(.002)
        root.update()
        records.append({'click_handler_ms': round((returned-start)*1000, 2),
                        'list_ready_ms': round((time.perf_counter()-start)*1000, 2),
                        'models': len(app.profile_choices), 'rendered_cards': len(app.profile_cards)})
    assert not errors, errors
    report = {'fixture_backups': 120, 'runs': records,
              'max_heartbeat_gap_ms': round(max(gaps, default=0), 2)}
    root.destroy()
(args.output / 'model-list.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
