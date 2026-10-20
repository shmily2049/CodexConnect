"""Credential-free model registry; v1 tombstones migrate on the next confirmed write."""
import json
import re
from dataclasses import replace

MAX_STATE = 1024 * 1024


def state_path(config):
    return config.parent / 'provider-tool-profiles.json'


def parse_state(raw):
    from provider_core import ConfigError
    if raw is None:
        return {'version': 1, 'hidden': []}
    try:
        data = json.loads(raw)
        hidden = data['hidden']
        if len(raw) > MAX_STATE or data.get('version') not in (1, 2):
            raise ValueError()
        if not isinstance(hidden, list) or not all(isinstance(x, str) and re.fullmatch('[0-9a-f]{64}', x) for x in hidden):
            raise ValueError()
        if data['version'] == 2:
            from switch_profiles import _choice, FIELDS
            if not isinstance(data.get('choices'), list):
                raise ValueError()
            seen = set()
            for item in data['choices']:
                fields = item['fields']
                if not isinstance(fields, dict) or set(fields) - set(FIELDS):
                    raise ValueError()
                if any(not isinstance(value, str) for key, value in fields.items() if key != 'model_context_window'):
                    raise ValueError()
                if 'model_context_window' in fields and type(fields['model_context_window']) is not int:
                    raise ValueError()
                doc = dict(fields)
                if item['id'] != 'account':
                    doc['model_providers'] = {fields['model_provider']: {'name': item['name'], 'base_url': item['url']}}
                normalized = _choice(doc)
                if normalized is None or normalized != item or item['id'] in seen:
                    raise ValueError()
                seen.add(item['id'])
        return data
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ConfigError('方案管理文件损坏，请保留文件后检查。') from None


def read_state(config):
    from provider_core import ConfigError
    path = state_path(config)
    if path.is_symlink():
        raise ConfigError('方案管理文件是符号链接，已停止操作。')
    if not path.exists():
        return None, set()
    if not path.is_file() or path.stat().st_size > MAX_STATE:
        raise ConfigError('方案管理文件类型或大小异常。')
    raw = path.read_bytes()
    return raw, set(parse_state(raw)['hidden'])


def encode(hidden, items=None):
    data = {'version': 1 if items is None else 2, 'hidden': sorted(hidden)}
    if items is not None:
        data['choices'] = [{k: v for k, v in item.items() if k != 'current'} for item in items]
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
    parse_state(raw)
    return raw


def decorate_plan(plan, retired=None, *, resolved=None):
    from switch_profiles import _choice, choices
    from provider_core import parse_config
    before, hidden = read_state(plan.snapshot.path)
    if resolved is None:
        resolved_items = choices(plan.snapshot)
    else:
        expected, resolved_items = resolved
        assert_state(plan.snapshot.path, expected)
        before = expected
    items = {item['id']: item for item in resolved_items}
    item = _choice(parse_config(plan.updated))
    if retired:
        hidden.add(retired)
    if item:
        hidden.discard(item['id'])
        items[item['id']] = item
    assert_state(plan.snapshot.path, before)
    return replace(plan, profile_state_before=before,
                   profile_state_after=encode(hidden, items.values()))


def assert_state(config, expected):
    from provider_core import ConfigError
    if read_state(config)[0] != expected:
        raise ConfigError('模型方案已被其他窗口修改，请刷新后重试。')


def resolve_choices(snap):
    """Read one consistent registry view for a subsequent checked operation."""
    from switch_profiles import choices
    from provider_core import _assert_unchanged
    before = read_state(snap.path)[0]
    items = choices(snap)
    assert_state(snap.path, before)
    _assert_unchanged(snap)
    return before, items


def delete_choice(snap, choice_id, *, resolved=None):
    from provider_core import ConfigError, _lock, _assert_unchanged, _atomic_write, digest
    from switch_profiles import choices
    lock = _lock(snap.path)
    try:
        _assert_unchanged(snap)
        before, hidden = read_state(snap.path)
        if resolved is None:
            items = choices(snap)
        else:
            expected, items = resolved
            assert_state(snap.path, expected)
            before = expected
        item = next((x for x in items if x['id'] == choice_id), None)
        if item is None:
            raise ConfigError('方案已变化，请刷新列表。')
        if choice_id == 'account':
            raise ConfigError('ChatGPT套餐是内置入口，无需删除。')
        if item['current']:
            raise ConfigError('请先切换到其他模型或 ChatGPT套餐，再删除此方案。')
        hidden.add(choice_id)
        backup = snap.path.parent / 'provider-tool-profile-backups' / (digest(before or b'') + '.json')
        _atomic_write(backup, before or encode(set()))
        _assert_unchanged(snap)
        assert_state(snap.path, before)
        _atomic_write(state_path(snap.path), encode(hidden, items))
    finally:
        lock.unlink(missing_ok=True)
