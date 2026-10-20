"""Local Codex provider configuration. No network or writes on import."""
from __future__ import annotations

import copy
import difflib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import tomlkit

VERSION = '0.10.13'
DEEPSEEK_DOC = 'https://api-docs.deepseek.com/quick_start/agent_integrations/codex/'
MAX_CONFIG = 5 * 1024 * 1024
MAX_CATALOG = 3 * 1024 * 1024


class ConfigError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_config() -> Path:
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser() / 'config.toml'


@dataclass(frozen=True)
class Snapshot:
    path: Path
    exists: bool
    raw: bytes

    @property
    def sha(self):
        return digest(self.raw) if self.exists else None


@dataclass(frozen=True)
class Settings:
    provider: str
    name: str
    model: str
    base_url: str
    auth_mode: str = 'env'
    env_key: str = 'DEEPSEEK_API_KEY'
    token: str = ''
    reasoning: str = ''
    catalog_path: str = ''
    catalog_bytes: bytes | None = None
    context_window: int | None = None


@dataclass(frozen=True)
class Plan:
    snapshot: Snapshot
    updated: bytes
    preview: str
    catalog_target: Path | None = None
    catalog_bytes: bytes | None = None
    profile_state_before: bytes | None = None
    profile_state_after: bytes | None = None


def read_snapshot(path: str | Path) -> Snapshot:
    path = Path(path).expanduser().absolute()
    if path.name != 'config.toml':
        raise ConfigError('请选择名为 config.toml 的配置文件。')
    if path.is_symlink():
        raise ConfigError('配置文件是符号链接。请明确选择其真实目标路径。')
    path = path.parent.resolve() / path.name
    if path.exists():
        if not path.is_file() or path.stat().st_size > MAX_CONFIG:
            raise ConfigError('配置文件类型或大小不符合要求。')
        raw = path.read_bytes()
        parse_config(raw)
        return Snapshot(path, True, raw)
    return Snapshot(path, False, b'')


def parse_config(raw: bytes):
    try:
        return tomlkit.parse(raw.decode('utf-8-sig'))
    except Exception:
        # Parser exceptions can include a line containing a credential.
        raise ConfigError('配置不是有效的 UTF-8 TOML；请先修复语法，原文件未修改。') from None


def check_url(value: str) -> str:
    value = value.strip().rstrip('/')
    try:
        u = urllib.parse.urlsplit(value)
        _ = u.port
    except ValueError:
        raise ConfigError('API 地址无效。') from None
    local = u.hostname == 'localhost'
    try:
        local = local or ipaddress.ip_address(u.hostname or '').is_loopback
    except ValueError:
        pass
    if not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ConfigError('API 地址必须包含主机名，且不能包含用户名、密码、查询参数或片段。')
    if any(c in value for c in '{}<>'):
        raise ConfigError('API 地址仍含占位符，请填写完整的真实地址。')
    if u.scheme != 'https' and not (u.scheme == 'http' and local):
        raise ConfigError('远程服务必须使用 HTTPS；只有本机回环地址允许 HTTP。')
    if any(c.isspace() for c in value):
        raise ConfigError('API 地址不能包含空白字符。')
    if u.path.rstrip('/').endswith(('/responses', '/chat/completions', '/models')):
        raise ConfigError('请填写基础地址，例如 https://api.deepseek.com，而不是完整 API 方法路径。')
    return value


def suggested_provider_id(base_url: str) -> str:
    """Stable identifier from the endpoint, independent of display/model names."""
    url = check_url(base_url)
    if url == 'https://api.deepseek.com':
        return 'deepseek'
    host = urllib.parse.urlsplit(url).hostname or 'service'
    slug = re.sub(r'[^a-z0-9]+', '_', host.lower()).strip('_')[:25] or 'service'
    return 'svc_' + slug + '_' + digest(url.encode())[:10]


def resolve_provider_id(snap: Snapshot, base_url: str, preferred: str = '') -> str:
    """Reuse the loaded matching service, otherwise allocate without clobbering."""
    url = check_url(base_url)
    providers = parse_config(snap.raw).get('model_providers', {})
    if not isinstance(providers, dict):
        raise ConfigError('现有服务配置格式不正确，请检查 config.toml；原文件未修改。')
    def matches(key):
        item = providers.get(key)
        return isinstance(item, dict) and str(item.get('base_url', '')).rstrip('/') == url
    if (re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', preferred)
            and preferred not in {'openai', 'ollama', 'lmstudio', 'amazon-bedrock'} and matches(preferred)):
        return preferred
    base = suggested_provider_id(url)
    candidate = base
    index = 1
    while candidate in providers:
        if matches(candidate):
            return candidate
        candidate = base + '_' + str(index)
        index += 1
        if index > 10000:
            raise ConfigError('现有服务条目过多，无法自动分配标识；原文件未修改。')
    return candidate


def validate_catalog(raw: bytes, model: str = '') -> dict:
    if len(raw) > MAX_CATALOG:
        raise ConfigError('模型目录大于 3 MB。')
    try:
        obj = json.loads(raw)
    except Exception:
        raise ConfigError('模型目录不是有效 JSON。') from None
    models = obj.get('models') if isinstance(obj, dict) else None
    if not isinstance(models, list) or not models:
        raise ConfigError('需要 Codex 模型目录：顶层 models 必须是非空数组。')
    slugs = []
    for entry in models:
        if not isinstance(entry, dict) or not isinstance(entry.get('slug'), str):
            raise ConfigError('每个模型条目必须包含字符串 slug。')
        slugs.append(entry['slug'])
    if len(slugs) != len(set(slugs)):
        raise ConfigError('模型目录中存在重复 slug。')
    if model and model not in slugs:
        raise ConfigError('模型目录中没有所选模型，请核对模型 ID。')
    return obj


def validate_settings(s: Settings):
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}', s.provider):
        raise ConfigError('Provider ID 需以字母开头，只能包含字母、数字、下划线或连字符。')
    if s.provider in {'openai', 'ollama', 'lmstudio', 'amazon-bedrock'}:
        raise ConfigError('这是内置 Provider ID，请使用自己的标识，如 my_gateway。')
    if not s.name.strip() or not s.model.strip() or any(c.isspace() for c in s.model):
        raise ConfigError('请填写显示名称和不含空格的模型 ID。')
    check_url(s.base_url)
    if s.auth_mode == 'env':
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s.env_key):
            raise ConfigError('环境变量名格式不正确。')
    elif s.auth_mode == 'token':
        if not s.token.strip() or any(c.isspace() for c in s.token):
            raise ConfigError('请填写不含空白字符的 API Key。')
    else:
        raise ConfigError('不支持的鉴权模式。')
    if s.reasoning not in {'', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}:
        raise ConfigError('推理级别无效。')
    if s.context_window is not None and (type(s.context_window) is not int or not 1 <= s.context_window <= 100_000_000):
        raise ConfigError('上下文长度需为 1 到 100000000 的整数，或留空。')


def safe_summary(doc, target_provider: str):
    keys = ('model', 'model_provider', 'forced_login_method', 'model_reasoning_effort',
            'web_search', 'model_catalog_json', 'model_context_window')
    obj = {k: doc[k].unwrap() if hasattr(doc[k], 'unwrap') else doc[k] for k in keys if k in doc}
    providers = doc.get('model_providers', {})
    if not isinstance(providers, dict):
        raise ConfigError('现有 model_providers 不是表。')
    provider = providers.get(target_provider, {})
    if not isinstance(provider, dict):
        raise ConfigError('现有 Provider 不是表。')
    allowed = ('name', 'base_url', 'wire_api', 'env_key', 'requires_openai_auth')
    data = {k: provider[k].unwrap() if hasattr(provider[k], 'unwrap') else provider[k] for k in allowed if k in provider}
    if 'base_url' in data:
        try:
            u = urllib.parse.urlsplit(data['base_url'])
            host = u.hostname or ''
            if ':' in host:
                host = '[' + host + ']'
            if u.port is not None:
                host += ':' + str(u.port)
            data['base_url'] = urllib.parse.urlunsplit((u.scheme, host, u.path, '', ''))
        except ValueError:
            data['base_url'] = '<旧地址已隐藏>'
    if 'experimental_bearer_token' in provider:
        data['experimental_bearer_token'] = '<已隐藏 API Key>'
    if 'auth' in provider:
        data['auth'] = '<已有命令鉴权>'
    obj['model_providers.' + target_provider] = data
    return json.dumps(obj, ensure_ascii=False, indent=2).splitlines(True)


def validate_compatibility(doc):
    if doc.get('profile') or doc.get('profiles'):
        raise ConfigError('检测到旧式 profile 配置，当前 Codex 已不再支持。请先迁移到独立的 profile-name.config.toml，并通过 --profile 选择；原配置未修改。')


def prepare(snap: Snapshot, s: Settings, *, retired=None, resolved=None) -> Plan:
    validate_settings(s)
    doc = parse_config(snap.raw)
    validate_compatibility(doc)
    before = safe_summary(doc, s.provider)
    providers = doc.get('model_providers')
    if providers is not None and not isinstance(providers, dict):
        raise ConfigError('现有 model_providers 不是表。')
    if providers is None:
        doc['model_providers'] = tomlkit.table()
    providers = doc['model_providers']
    if s.provider not in providers:
        providers[s.provider] = tomlkit.table()
    pr = providers[s.provider]
    if not isinstance(pr, dict):
        raise ConfigError('现有 Provider 不是表。')
    if pr.get('base_url') and str(pr['base_url']).rstrip('/') != check_url(s.base_url):
        raise ConfigError('同名 Provider 已指向不同地址。请使用新 Provider ID，以免继承旧服务的凭据或请求头。')
    for auth_field in ('env_key', 'env_key_instructions', 'experimental_bearer_token', 'auth', 'requires_openai_auth'):
        pr.pop(auth_field, None)
    for header_group in ('http_headers', 'env_http_headers'):
        if header_group in pr:
            for k in list(pr[header_group]):
                if k.lower() in {'authorization', 'x-api-key', 'api-key'}:
                    del pr[header_group][k]
    pr['name'] = s.name.strip()
    pr['base_url'] = check_url(s.base_url)
    pr['wire_api'] = 'responses'
    pr['requires_openai_auth'] = False
    pr['env_key' if s.auth_mode == 'env' else 'experimental_bearer_token'] = s.env_key if s.auth_mode == 'env' else s.token
    doc['model'] = s.model
    if s.context_window is not None:
        doc['model_context_window'] = s.context_window
    else:
        doc.pop('model_context_window', None)
    doc['model_provider'] = s.provider
    # Third-party credentials are provider-specific. Forcing API login can
    # invalidate a cached ChatGPT login, even though this provider needs no OAuth.
    if doc.get('forced_login_method') == 'api':
        doc.pop('forced_login_method', None)
    doc['web_search'] = 'disabled'
    if s.reasoning:
        doc['model_reasoning_effort'] = s.reasoning
    else:
        doc.pop('model_reasoning_effort', None)
    # Own a content-addressed copy so display labels never modify the imported file.
    from model_catalog import display_catalog
    imported = None
    if s.catalog_bytes is not None:
        imported = validate_catalog(s.catalog_bytes, s.model)
    elif s.catalog_path.strip():
        path = Path(s.catalog_path).expanduser()
        if not path.is_absolute():
            path = snap.path.parent / path
        path = path.resolve()
        if not path.is_file() or path.stat().st_size > MAX_CATALOG:
            raise ConfigError('模型目录文件不存在或超过 3 MB。')
        imported = validate_catalog(path.read_bytes(), s.model)
    if imported is None and (s.provider == 'deepseek' or urllib.parse.urlsplit(check_url(s.base_url)).hostname == 'api.deepseek.com'):
        raise ConfigError('DeepSeek 官方服务需要模型目录。请点击“获取官方目录”或选择本地 models.json。')
    try:
        catalog_bytes = display_catalog(s.model, imported)
    except (OSError, ValueError, KeyError):
        raise ConfigError('名称同步所需的应用文件缺失或损坏，请重新下载完整应用。') from None
    validate_catalog(catalog_bytes, s.model)
    catalog_target = snap.path.parent / 'provider-tool-catalogs' / (digest(catalog_bytes) + '.json')
    doc['model_catalog_json'] = catalog_target.as_posix()
    updated = tomlkit.dumps(doc).encode('utf-8')
    parse_config(updated)
    preview = ''.join(difflib.unified_diff(before, safe_summary(doc, s.provider), fromfile='保存前', tofile='保存后'))
    # Redact token literals even if user pasted them in another form field.
    if s.token:
        preview = preview.replace(s.token, '<已隐藏 API Key>')
    from profile_store import decorate_plan
    return decorate_plan(Plan(snap, updated, preview or '配置字段没有变化。', catalog_target, catalog_bytes), retired, resolved=resolved)


def _assert_unchanged(snap: Snapshot):
    now = read_snapshot(snap.path)
    if (now.exists, now.raw) != (snap.exists, snap.raw):
        raise ConfigError('配置已被其他程序修改。请重新加载并预览，不会覆盖新内容。')


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.provider-tool-', dir=path.parent)
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _backup(snap: Snapshot, after: bytes | None, operation: str, *,
            profiles_before=None, profiles_after=None, include_profiles=False) -> Path:
    root = snap.path.parent / 'provider-tool-backups'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    dest = root / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    dest.mkdir(mode=0o700)
    if snap.exists:
        _atomic_write(dest / 'original.config.toml', snap.raw)
    manifest = {'version': 1, 'operation': operation, 'config_path': str(snap.path),
                'before_exists': snap.exists, 'before_sha256': snap.sha,
                'after_sha256': digest(after) if after is not None else None}
    def model_label(raw):
        doc = parse_config(raw or b'')
        return str(doc.get('model', 'ChatGPT套餐 / 默认模型'))[:100]
    manifest['before_model'] = model_label(snap.raw)
    manifest['after_model'] = model_label(after)
    if include_profiles:
        manifest['profiles'] = {'before_exists': profiles_before is not None,
                               'before_sha256': digest(profiles_before) if profiles_before is not None else None,
                               'after_sha256': digest(profiles_after) if profiles_after is not None else None}
        if profiles_before is not None:
            _atomic_write(dest / 'original.profiles.json', profiles_before)
    _atomic_write(dest / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    return dest


def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / '.provider-tool.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ConfigError('另一个配置工具正在写入，或上次异常退出留下锁文件。确认工具均已关闭后再检查 .provider-tool.lock。') from None
    os.close(fd)
    return lock


def apply_plan(plan: Plan) -> Path:
    snap = plan.snapshot
    lock = _lock(snap.path)
    try:
        _assert_unchanged(snap)
        from profile_store import assert_state, state_path
        if plan.profile_state_after is not None:
            assert_state(snap.path, plan.profile_state_before)
        backup = _backup(snap, plan.updated, 'save', profiles_before=plan.profile_state_before,
                         profiles_after=plan.profile_state_after, include_profiles=plan.profile_state_after is not None)
        if plan.catalog_target and plan.catalog_bytes is not None:
            if plan.catalog_target.exists():
                if plan.catalog_target.read_bytes() != plan.catalog_bytes:
                    raise ConfigError('已有同名模型目录内容异常，已停止保存。')
            else:
                _atomic_write(plan.catalog_target, plan.catalog_bytes)
        _assert_unchanged(snap)
        if plan.profile_state_after is not None:
            assert_state(snap.path, plan.profile_state_before)
            _atomic_write(state_path(snap.path), plan.profile_state_after)
        try:
            _assert_unchanged(snap)
            _atomic_write(snap.path, plan.updated)
        except Exception:
            if plan.profile_state_after is not None:
                assert_state(snap.path, plan.profile_state_after)
                if plan.profile_state_before is None:
                    state_path(snap.path).unlink(missing_ok=True)
                else:
                    _atomic_write(state_path(snap.path), plan.profile_state_before)
            raise
        if snap.path.read_bytes() != plan.updated:
            raise ConfigError('保存后校验失败，请检查备份。')
        return backup
    finally:
        lock.unlink(missing_ok=True)


def list_backups(config: Path) -> list[Path]:
    root = config.parent / 'provider-tool-backups'
    if not root.exists():
        return []
    backups = [p for p in root.iterdir() if p.is_dir() and (p / 'manifest.json').is_file()]
    # Names contain a random suffix; lexical sorting is not chronological within a second.
    return sorted(backups, key=lambda p: ((p / 'manifest.json').stat().st_mtime_ns, p.name), reverse=True)


def restore_backup(config: Path, backup: Path) -> Path:
    snap = read_snapshot(config)
    expected_root = (snap.path.parent / 'provider-tool-backups').resolve()
    backup = backup.resolve()
    if backup.parent != expected_root:
        raise ConfigError('备份必须位于当前配置的备份目录中。')
    meta = read_backup_manifest(backup)
    if meta.get('config_path') != str(snap.path) or meta.get('version') != 1:
        raise ConfigError('此备份不属于当前配置文件。')
    if snap.sha != meta.get('after_sha256'):
        raise ConfigError('当前配置与该备份之后的版本不同，拒绝覆盖后续修改。可在文件管理器中检查备份并手动合并。')
    original = (backup / 'original.config.toml').read_bytes() if meta['before_exists'] else None
    if original is not None:
        if digest(original) != meta.get('before_sha256'):
            raise ConfigError('备份校验失败。')
        parse_config(original)
    from profile_store import read_state, parse_state, assert_state, state_path, decorate_plan
    state_before = read_state(snap.path)[0]
    profile_meta = meta.get('profiles')
    if profile_meta is not None:
        if (digest(state_before) if state_before is not None else None) != profile_meta.get('after_sha256'):
            raise ConfigError('模型方案已有后续改动，恢复已停止，避免覆盖这些改动。请查看备份。')
        state_after = (backup / 'original.profiles.json').read_bytes() if profile_meta['before_exists'] else None
        if (digest(state_after) if state_after is not None else None) != profile_meta.get('before_sha256'):
            raise ConfigError('方案备份校验失败。')
        parse_state(state_after)
    else:
        # Preserve state for legacy backups without verified profile metadata,
        # but allow the restored current choice to be selected again later.
        state_after = decorate_plan(Plan(snap, original or b'', '')).profile_state_after
    lock = _lock(snap.path)
    try:
        _assert_unchanged(snap)
        assert_state(snap.path, state_before)
        safety = _backup(snap, original, 'restore', profiles_before=state_before,
                         profiles_after=state_after, include_profiles=True)
        _assert_unchanged(snap)
        assert_state(snap.path, state_before)
        if state_after is None:
            state_path(snap.path).unlink(missing_ok=True)
        else:
            _atomic_write(state_path(snap.path), state_after)
        try:
            _assert_unchanged(snap)
            if original is None:
                snap.path.unlink(missing_ok=True)
            else:
                _atomic_write(snap.path, original)
        except Exception:
            assert_state(snap.path, state_after)
            if state_before is None:
                state_path(snap.path).unlink(missing_ok=True)
            else:
                _atomic_write(state_path(snap.path), state_before)
            raise
        return safety
    finally:
        lock.unlink(missing_ok=True)


def read_backup_manifest(backup):
    """Reject malformed metadata before it can participate in a restore."""
    try:
        path = backup / 'manifest.json'
        if path.stat().st_size > 16384:
            raise ValueError()
        meta = json.loads(path.read_text('utf-8'))
        if not isinstance(meta, dict) or meta.get('version') != 1:
            raise ValueError()
        if not isinstance(meta.get('config_path'), str) or type(meta.get('before_exists')) is not bool:
            raise ValueError()
        def valid_hash(value):
            return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None
        if 'after_sha256' not in meta or not (meta['after_sha256'] is None or valid_hash(meta['after_sha256'])):
            raise ValueError()
        if not (valid_hash(meta.get('before_sha256')) if meta['before_exists'] else meta.get('before_sha256') is None):
            raise ValueError()
        if 'profiles' in meta:
            profiles = meta['profiles']
            if not isinstance(profiles, dict) or type(profiles.get('before_exists')) is not bool:
                raise ValueError()
            if not (valid_hash(profiles.get('before_sha256')) if profiles['before_exists'] else profiles.get('before_sha256') is None):
                raise ValueError()
            if 'after_sha256' not in profiles or not (profiles['after_sha256'] is None or valid_hash(profiles['after_sha256'])):
                raise ValueError()
        return meta
    except (OSError, ValueError, TypeError, KeyError):
        raise ConfigError('备份清单损坏或无法读取，不能恢复此备份。') from None


def backup_description(snap, backup, *, state=...):
    """Display model metadata, never provider credentials or raw TOML."""
    try:
        meta = read_backup_manifest(backup)
        stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.strptime(backup.name[:15], '%Y%m%d-%H%M%S'))
        eligible = meta.get('config_path') == str(snap.path) and meta.get('after_sha256') == snap.sha
        if 'profiles' in meta:
            from profile_store import read_state
            raw = read_state(snap.path)[0] if state is ... else state
            eligible = eligible and meta['profiles'].get('after_sha256') == (digest(raw) if raw is not None else None)
        label = ('可恢复' if eligible else '有后续改动') + ' · ' + stamp
        operation = '恢复前备份' if meta.get('operation') == 'restore' else '保存前备份'
        return label + ' · ' + operation + ' · ' + str(meta.get('before_model', '旧配置')) + ' → ' + str(meta.get('after_model', '新配置'))
    except (OSError, ValueError, TypeError, ConfigError):
        return '备份损坏或无法读取 · ' + backup.name


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(req, limit: int):
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=20) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ConfigError('服务返回内容超出大小限制。')
        return data


class CodeBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks, self.current, self.depth = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag == 'code':
            self.depth += 1
            if self.depth == 1:
                self.current = []

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'code' and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self.blocks.append(''.join(self.current))


def fetch_deepseek_catalog() -> bytes:
    try:
        raw = _request(urllib.request.Request(DEEPSEEK_DOC, headers={'User-Agent': 'CodexProviderTool/0.1'}), MAX_CATALOG)
        parser = CodeBlocks()
        parser.feed(raw.decode('utf-8'))
        for block in parser.blocks:
            if block.strip().startswith('{'):
                try:
                    obj = validate_catalog(block.encode('utf-8'))
                    if 'deepseek-flash' in [m['slug'] for m in obj['models']]:
                        return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                except ConfigError:
                    continue
    except Exception:
        raise ConfigError('无法获取 DeepSeek 官方目录；可打开官方页面手动保存 models.json，然后导入。') from None
    raise ConfigError('官方页面结构或模型目录已变化，自动导入已停止；请手动导入。')


def test_connection(s: Settings) -> str:
    validate_settings(s)
    key = s.token if s.auth_mode == 'token' else os.environ.get(s.env_key, '')
    if not key:
        raise ConfigError('当前工具进程未读取到这个环境变量。重新启动工具，或切换为 API Key 模式后测试。')
    body = {'model': s.model, 'input': 'Reply with exactly OK.', 'stream': False, 'max_output_tokens': 128, 'store': False}
    if urllib.parse.urlsplit(check_url(s.base_url)).hostname == 'api.deepseek.com':
        body['reasoning'] = {'effort': 'low'}
    req = urllib.request.Request(check_url(s.base_url) + '/responses',
                                 data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key,
                                          'User-Agent': 'codex'},
                                 method='POST')
    try:
        data = json.loads(_request(req, 1024 * 1024))
    except urllib.error.HTTPError as err:
        status = err.code
        err.close()
        tips = {401: '鉴权失败，检查 API Key。', 403: '服务拒绝访问或模型权限不足。',
                404: '地址或模型不存在，或服务不支持 Responses API。', 429: '请求受限，请检查速率或账户额度。'}
        raise ConfigError(f'HTTP {status}：' + tips.get(status, '服务未成功响应；不会显示可能包含凭据的原始错误体。')) from None
    except ConfigError:
        raise
    except Exception:
        raise ConfigError('网络、TLS 或响应格式异常。未验证成功；请检查地址和网络连接。') from None
    if not isinstance(data, dict) or data.get('object') != 'response' or not isinstance(data.get('output'), list):
        raise ConfigError('收到响应，但不是预期的 Responses API 对象；不能据此确认兼容。')
    texts = []
    for item in data['output']:
        if isinstance(item, dict) and item.get('type') == 'message':
            contents = item.get('content')
            if not isinstance(contents, list):
                raise ConfigError('接口返回了 Responses 对象，但文字回复格式异常；尚未通过测试。')
            for content in contents:
                if isinstance(content, dict) and content.get('type') == 'output_text':
                    value = content.get('text')
                    if not isinstance(value, str):
                        raise ConfigError('接口返回了 Responses 对象，但文字回复格式异常；尚未通过测试。')
                    if value.strip():
                        texts.append(value)
    if data.get('status') != 'completed' or not texts:
        raise ConfigError('接口返回了 Responses 对象，但没有完成文字回复；可能达到输出限制，尚未通过测试。')
    answer = '\n'.join(texts).replace(key, '<API Key>')[:300]
    return '已收到 Responses API 文字回复：\n' + answer + '\n\n这里只验证短文本请求；Codex 工具调用、流式输出和多轮会话仍需在客户端验证。'
