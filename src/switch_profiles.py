"""Derive reusable model choices from verified local backups; never read auth caches."""
from pathlib import Path
import copy
import difflib
import json
from provider_core import (ConfigError, Plan, Snapshot, MAX_CONFIG, MAX_CATALOG,
    parse_config, read_snapshot, list_backups, digest, check_url, safe_summary,
    validate_catalog, validate_compatibility, tomlkit)

FIELDS = ('model', 'model_provider', 'model_reasoning_effort', 'web_search', 'model_catalog_json', 'model_context_window')


def selection(doc):
    return {k: copy.deepcopy(doc[k].unwrap() if hasattr(doc[k], 'unwrap') else doc[k])
            for k in FIELDS if k in doc}


def _choice(doc):
    pid = str(doc.get('model_provider', 'openai'))
    if pid == 'openai':
        if doc.get('forced_login_method') == 'api' or doc.get('openai_base_url'):
            return None
        return {'id': 'account', 'label': 'ChatGPT套餐', 'fields': selection(doc), 'url': ''}
    providers = doc.get('model_providers', {})
    if not isinstance(providers, dict):
        return None
    provider = providers.get(pid, {})
    if not isinstance(provider, dict) or not doc.get('model'):
        return None
    try:
        url = check_url(str(provider.get('base_url', '')))
    except ConfigError:
        return None
    fields = selection(doc)
    identity = {k:v for k,v in fields.items() if k != 'model_catalog_json'}
    key = digest(json.dumps([identity, url], sort_keys=True, ensure_ascii=False).encode())
    name = str(provider.get('name', pid))
    return {'id': key, 'name': name, 'label': name + ' · ' + str(doc['model']),
            'fields': fields, 'url': url}


def choices(snap, *, history_cache=None):
    """Newest occurrence wins; only verified backups for this exact config count."""
    result = {'account': {'id': 'account', 'label': 'ChatGPT套餐', 'fields': {}, 'url': ''}}
    from profile_store import read_state, parse_state
    state_raw, hidden = read_state(snap.path)
    state = parse_state(state_raw)
    if state['version'] == 2:
        result.update({item['id']: copy.deepcopy(item) for item in state['choices']})
    for backup in reversed(list_backups(snap.path) if state['version'] == 1 else []):
        try:
            if backup.is_symlink():
                continue
            meta_path, raw_path = backup / 'manifest.json', backup / 'original.config.toml'
            if meta_path.is_symlink() or raw_path.is_symlink() or meta_path.stat().st_size > 16384:
                continue
            meta = json.loads(meta_path.read_text('utf-8'))
            if meta.get('version') != 1 or meta.get('config_path') != str(snap.path):
                continue
            if not meta.get('before_exists'):
                raw = b''
            else:
                if raw_path.stat().st_size > MAX_CONFIG:
                    continue
                raw = raw_path.read_bytes()
                if digest(raw) != meta.get('before_sha256'):
                    continue
            # UI-only cache stores normalized, credential-free metadata. Always read
            # and verify the actual bytes first; save/switch paths do not use it.
            cache_key = digest(raw)
            if history_cache is not None and cache_key in history_cache:
                item = copy.deepcopy(history_cache[cache_key])
            else:
                item = _choice(parse_config(raw))
                if history_cache is not None:
                    if len(history_cache) >= 256:
                        history_cache.pop(next(iter(history_cache)))
                    history_cache[cache_key] = copy.deepcopy(item)
            if item:
                result[item['id']] = item
        except (OSError, ValueError, ConfigError, AttributeError, TypeError):
            continue
    current = _choice(parse_config(snap.raw))
    if current:
        result[current['id']] = current
    for item in result.values():
        item['current'] = current is not None and item['id'] == current['id']
    return [item for item in result.values() if item['current'] or item['id'] not in hidden]


def prepare_switch(snap: Snapshot, choice_id: str, *, reset_account_url=False) -> Plan:
    return prepare_switch_review(snap, choice_id, reset_account_url=reset_account_url)[0]


def prepare_switch_review(snap: Snapshot, choice_id: str, *, reset_account_url=False):
    """Use one freshly verified selection for both confirmation and the write plan."""
    from profile_store import read_state, assert_state
    state_before = read_state(snap.path)[0]
    doc = parse_config(snap.raw)
    validate_compatibility(doc)
    items = choices(snap)
    assert_state(snap.path, state_before)
    item = next((p for p in items if p['id'] == choice_id), None)
    if item is None:
        raise ConfigError('方案已变化，请刷新列表后重新选择。')
    fields = item['fields']
    pid = str(fields.get('model_provider', 'openai'))
    providers = doc.get('model_providers', {})
    if choice_id == 'account':
        if providers.get('openai'):
            raise ConfigError('当前覆盖了内置 OpenAI 服务。请先检查高级配置，再使用 ChatGPT套餐入口。')
        if doc.get('openai_base_url') and not reset_account_url:
            raise ConfigError('存在 OpenAI 地址覆盖，请选择“恢复默认地址并切回套餐”；原配置会备份。')
    else:
        pr = providers.get(pid)
        if not isinstance(pr, dict) or check_url(str(pr.get('base_url', ''))) != item['url']:
            raise ConfigError('该方案的服务配置已删除或地址已改变。请在“模型连接”重新配置，避免使用错误的密钥。')
        if pr.get('wire_api') != 'responses' or pr.get('requires_openai_auth') is not False:
            raise ConfigError('此服务的鉴权或接口设置不支持快速切换，请在“模型连接”重新配置。')
        if not (pr.get('env_key') or pr.get('experimental_bearer_token')):
            raise ConfigError('该服务未保存密钥或环境变量，请先补充连接配置。')
    catalog_target, catalog_bytes = None, None
    imported = None
    catalog = fields.get('model_catalog_json')
    if catalog:
        path = Path(catalog).expanduser()
        if not path.is_absolute():
            path = snap.path.parent / path
        if not path.is_file() or path.stat().st_size > MAX_CATALOG:
            raise ConfigError('方案所需的模型目录已丢失，请重新获取目录并保存。')
        imported = validate_catalog(path.read_bytes(), str(fields.get('model', '')))
    before = safe_summary(doc, pid)
    if choice_id != 'account':
        providers[pid]['name'] = item['name']
    for key in FIELDS:
        if key in fields:
            doc[key] = fields[key]
        else:
            doc.pop(key, None)
    if choice_id == 'account':
        if reset_account_url:
            doc.pop('openai_base_url', None)
        doc['model_provider'] = 'openai'
        doc['forced_login_method'] = 'chatgpt'
    elif doc.get('forced_login_method') == 'api':
        doc.pop('forced_login_method', None)
    if choice_id != 'account':
        from model_catalog import display_catalog
        try:
            catalog_bytes = display_catalog(str(fields['model']), imported)
        except (OSError, ValueError, KeyError):
            raise ConfigError('名称同步所需的应用文件缺失或损坏，请重新下载完整应用。') from None
        validate_catalog(catalog_bytes, str(fields['model']))
        catalog_target = snap.path.parent / 'provider-tool-catalogs' / (digest(catalog_bytes) + '.json')
        doc['model_catalog_json'] = catalog_target.as_posix()
    updated = tomlkit.dumps(doc).encode('utf-8')
    parse_config(updated)
    preview = ''.join(difflib.unified_diff(before, safe_summary(doc, pid), fromfile='切换前', tofile='切换后'))
    from profile_store import decorate_plan
    plan = decorate_plan(Plan(snap, updated, preview or '已选择此方案，无需修改。', catalog_target, catalog_bytes),
                         resolved=(state_before, items))
    return plan, item['label']
