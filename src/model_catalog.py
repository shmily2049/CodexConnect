"""Offline model-picker catalogs; provider metadata overrides Codex fallback defaults."""
import copy
import json
from pathlib import Path
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def templates():
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets'
    fallback = json.loads((assets / 'codex-fallback-template.json').read_text(encoding='utf-8'))
    bundled = json.loads((assets / 'codex-bundled-models.json').read_text(encoding='utf-8'))
    return fallback, {entry['slug']: entry for entry in bundled['models']}


def display_catalog(model, catalog=None):
    """Return a new catalog, never mutate an imported object or invent provider capabilities.

    Unknown IDs use the upstream unknown-model fallback, not a GPT model entry.
    Provider-supplied values (including prompt, context and reasoning) win.
    Only the selected model's picker label and visibility are deliberately set.
    """
    fallback, known = templates()
    result = copy.deepcopy(catalog) if catalog is not None else {'models': [{'slug': model}]}
    entries = []
    for supplied in result['models']:
        slug = supplied['slug']
        if catalog is None:
            entry = copy.deepcopy(known.get(slug, fallback))
            entry.update(copy.deepcopy(supplied))
        else:
            # Do not add optional fallback capabilities to provider catalogs.
            entry = copy.deepcopy(supplied)
            for key in ('supported_reasoning_levels', 'shell_type', 'visibility',
                        'supported_in_api', 'priority', 'truncation_policy', 'support_verbosity',
                        'experimental_supported_tools'):
                entry.setdefault(key, copy.deepcopy(fallback[key]))
            messages = entry.get('model_messages')
            if not entry.get('base_instructions') and not (isinstance(messages, dict) and messages.get('instructions_template')):
                entry['base_instructions'] = fallback['base_instructions']
        # A provider instruction template must not compete with the fallback prompt.
        messages = supplied.get('model_messages')
        if isinstance(messages, dict) and messages.get('instructions_template') and 'base_instructions' not in supplied:
            entry.pop('base_instructions', None)
        entry['slug'] = slug
        if slug == model:
            entry['display_name'] = model
            entry['visibility'] = 'list'
        elif not supplied.get('display_name'):
            entry['display_name'] = slug
        entries.append(entry)
    result['models'] = entries
    return (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
