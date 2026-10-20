"""Repeatable offline UI benchmark; only uses an isolated fixture configuration."""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import statistics
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
results = {}
profiler = cProfile.Profile()
with tempfile.TemporaryDirectory(prefix='ui-perf-') as temp:
    config = Path(temp) / 'config.toml'
    config.write_text('model="fixture-model"\n', encoding='utf-8')
    profiler.enable()
    start = time.perf_counter()
    root = tk.Tk()
    app = App(root, config, show_welcome=False)
    root.update()
    results['startup_ms'] = round((time.perf_counter() - start) * 1000, 2)

    def measure(name, operation, count=20):
        samples = []
        for index in range(count):
            start = time.perf_counter()
            operation(index)
            root.update()
            samples.append((time.perf_counter() - start) * 1000)
        results[name] = {'median_ms': round(statistics.median(samples), 2),
                         'max_ms': round(max(samples), 2)}

    measure('typing', lambda i: app.vars['token'].set('FAKE-' + 'x' * i))
    def preset(index):
        app.vars['preset'].set('Kimi' if index % 2 else 'DeepSeek')
        app.preset_changed()
    measure('preset_change', preset)
    measure('page_switch', lambda i: app.tabs.select(4 if i % 2 else 0))
    measure('resize', lambda i: root.geometry(f'{980 + (i % 5) * 10}x700'))
    profiler.disable()
    root.destroy()
with (args.output / 'profile.txt').open('w', encoding='utf-8') as output:
    pstats.Stats(profiler, stream=output).sort_stats('cumulative').print_stats(55)
(args.output / 'timings.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
