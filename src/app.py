"""Cross-platform Tk desktop interface; real config is touched only on Save."""
from __future__ import annotations
import argparse
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
import webbrowser
from dataclasses import replace
from urllib.parse import urlsplit
from switch_profiles import choices
from desktop_restart import discover_desktop, restart_desktop
from provider_presets import get_preset, get_route, route_url, identify_preset, KEY_GUIDES

from provider_core import (VERSION, DEEPSEEK_DOC, ConfigError, Settings, default_config,
                           read_snapshot, parse_config, prepare, apply_plan, list_backups,
                           restore_backup, fetch_deepseek_catalog, validate_catalog, test_connection,
                           suggested_provider_id, resolve_provider_id, check_url)

REASONING_CHOICES = {'自动（由模型决定）': '', '不额外思考（none）': 'none',
                    '最少（minimal）': 'minimal', '较少（low）': 'low', '适中（medium）': 'medium',
                    '较高（high）': 'high', '很高（xhigh）': 'xhigh', '最大（max）': 'max', '极高（ultra）': 'ultra'}

def reasoning_label(value):
    return next((label for label, code in REASONING_CHOICES.items() if code == value), value)


class App:
    def __init__(self, root, config_path=None, show_welcome=None):
        self.root = root
        self.root.title('Codex Connect · 模型配置助手 ' + VERSION)
        self.plan = None
        self.catalog_bytes = None
        self.events = queue.Queue()
        self.busy = False
        self.backups = []
        self.backup_rows = []
        self.backup_pending = False
        self.revision = 0
        self.testing_revision = None
        self.loaded_provider = None
        self.editing_profile = None
        self.editing_state = None
        self.restart_running = False
        self.loading_preset = False
        self.summary_after_id = None
        self.profile_events = queue.Queue()
        self.profile_request = 0
        self.profile_loading = False
        self.profile_worker_running = False
        self.profile_pending = None
        self.profile_history_cache = {}
        self.profile_choices = []
        self.last_group_presets = {}
        from desktop_ui import build_ui
        build_ui(self, config_path or default_config(), VERSION, DEEPSEEK_DOC)
        self.preset_changed()
        self.mark_clean()
        for key, var in self.vars.items():
            if key != 'provider':
                var.trace_add('write', self.invalidate)
        self.vars['workspace'].trace_add('write', self.workspace_changed)
        self.vars['catalog'].trace_add('write', self.catalog_changed)
        self.vars['model'].trace_add('write', self.editing_model_changed)
        self.vars['config'].trace_add('write', self.profile_config_changed)
        self.sync_summary()
        self.welcome_marker = Path(self.vars['config'].get()).expanduser().parent / '.codex-connect-welcome'
        if show_welcome is None:
            show_welcome = not self.welcome_marker.is_file()
        if show_welcome:
            self.tabs.select(5)
        root.protocol('WM_DELETE_WINDOW', self.close_window)
        self.poll_after_id = root.after(100, self.poll)
        root.bind('<Destroy>', self.on_destroy, add='+')

    def on_destroy(self, event):
        if event.widget is self.root:
            for name in ('poll_after_id', 'summary_after_id'):
                pending = getattr(self, name, None)
                if pending is not None:
                    self.root.after_cancel(pending)
                    setattr(self, name, None)

    def open_manual(self):
        manual = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'manual.pdf'
        if not manual.is_file():
            messagebox.showerror('说明文件缺失', '请重新下载完整应用，PDF 使用说明已内置在安装包中。', parent=self.root)
            return
        try:
            if sys.platform == 'win32':
                import os
                os.startfile(str(manual))
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', str(manual)])
            else:
                webbrowser.open(manual.as_uri())
        except OSError:
            messagebox.showerror('无法打开使用说明', '请安装或设置默认 PDF 阅读器后重试。', parent=self.root)

    def finish_welcome(self, page):
        if page == 0 and getattr(self, 'editing_profile', None):
            if not self.start_add_model():
                return
        # This marker stores no settings or credentials and never replaces a file.
        try:
            self.welcome_marker.parent.mkdir(parents=True, exist_ok=True)
            with self.welcome_marker.open('x', encoding='utf-8') as marker:
                marker.write('welcome-seen-v1\n')
        except FileExistsError:
            pass
        except OSError:
            self.status.set('本次可以继续使用；下次打开时可能再次显示引导。')
        self.tabs.select(page)

    def close_window(self):
        if self.restart_running:
            messagebox.showinfo('正在重启', '请等待重启完成或失败提示后，再关闭配置助手。', parent=self.root)
            return
        if self.confirm_discard():
            self.root.destroy()

    def form_signature(self):
        return tuple((key, value.get()) for key, value in self.vars.items()
                     if key not in ('provider', 'preset', 'route'))

    def mark_clean(self):
        self.clean_form = self.form_signature()
        self.last_route = self.vars['route'].get()
        self.route_selection.set(self.last_route)

    def confirm_discard(self):
        return (not hasattr(self, 'clean_form') or self.form_signature() == self.clean_form
                or messagebox.askyesno('放弃未保存的修改？', '当前填写的内容还没有保存。继续会放弃这些修改。', parent=self.root))

    def start_add_model(self):
        if not self.confirm_discard():
            return
        self.preset_changed()
        self.invalidate()
        self.mark_clean()
        self.tabs.select(0)
        self.tabs.pages[0][1].yview_moveto(0)
        return True

    def choose_preset(self, key):
        if key == self.vars['preset'].get():
            return True
        if not self.confirm_discard():
            return False
        self.vars['preset'].set(key)
        self.preset_changed()
        return True

    def choose_route(self, *_):
        candidate = self.route_selection.get()
        if candidate == self.vars['route'].get():
            return
        if not self.confirm_discard():
            self.route_selection.set(self.vars['route'].get())
            return
        self.vars['route'].set(candidate)
        self.route_changed()

    def sync_summary(self):
        if self.summary_after_id is not None:
            self.root.after_cancel(self.summary_after_id)
            self.summary_after_id = None
        try:
            self.vars['provider'].set(self.preferred_provider() or suggested_provider_id(self.vars['base_url'].get()))
        except ConfigError:
            self.vars['provider'].set('填写地址后自动生成')
        model = self.vars['model'].get().strip() or '待填写模型'
        name = self.vars['name'].get().strip() or '自定义服务'
        self.summary.set(name[:24] + '  /  ' + model[:40])
        self.catalog_status.set('模型清单已就绪' if self.vars['catalog'].get() else '保存时自动同步模型名称')
        self.summary_name.set(name[:24])
        self.summary_model.set(model[:40])
        self.summary_auth.set('环境变量' if self.vars['auth'].get() == '环境变量（推荐）' else '本地 API Key')
        path = Path(self.vars['config'].get()).expanduser()
        self.summary_path.set('…/' + path.parent.name + '/' + path.name)
        for tile in self.provider_tiles:
            tile.set_selected(tile.preset_key == self.vars['preset'].get())
        for index, btn in enumerate(self.auth_buttons):
            btn.set_selected((index == 0) == (self.vars['auth'].get() == '环境变量（推荐）'))
        if self.vars['preset'].get() == 'DeepSeek':
            self.catalog_quick.pack(fill='x')
        else:
            self.catalog_quick.pack_forget()

    def invalidate(self, *_):
        self.error_action_button.grid_remove()
        self.plan = None
        self.revision += 1
        self.connection_state.set('尚未测试连接')
        self.footer_note.set('尚未保存当前改动')
        self.save_button.configure(state='disabled')
        self.preview_state.set('配置已变更 · 请重新下一步')
        self.preview_summary.set('填写完成后点击“下一步”，这里会说明将使用哪个模型。')
        self.success_panel.pack_forget()
        # Invalidate the save plan immediately; coalesce only decorative updates.
        if self.summary_after_id is None:
            self.summary_after_id = self.root.after_idle(self.sync_summary)

    def preset_changed(self, *_):
        self.clear_edit()
        self.loaded_provider = None
        preset = get_preset(self.vars['preset'].get())
        self.loading_preset = True
        self.vars['workspace'].set('')
        self.vars['route'].set(preset.routes[0].label)
        self.loading_preset = False
        self.route_changed()

    def preset_controls(self):
        preset = get_preset(self.vars['preset'].get())
        self.last_group_presets[preset.group] = preset.key
        route = get_route(preset.key, self.vars['route'].get())
        self.route_entry.configure(values=[r.label for r in preset.routes])
        self.model_entry.configure(values=route.models)
        self.route_group.pack_forget()
        self.route_note.pack_forget()
        brief = {
            'DeepSeek': '', 'Kimi': '', 'Grok': '',
            'OpenAI API': 'API 单独计费，不使用 ChatGPT 订阅额度。',
            '通义千问': '使用所选地域的按量付费密钥，不使用 Coding Plan 额度。',
            'Claude · OpenRouter': '由 OpenRouter 转发并计费，请使用 OpenRouter 密钥。',
            'Gemini · OpenRouter': '由 OpenRouter 转发并计费，请使用 OpenRouter 密钥。',
            '自定义 Responses 服务': '服务需要支持 Responses API。',
        }.get(preset.key, '使用此套餐专属密钥。' if '套餐' in route.label else '按量付费，不使用编程套餐额度。')
        self.route_note.configure(text=brief)
        if len(preset.routes) > 1:
            self.route_group.pack(fill='x', before=self.connection_fields)
        if brief:
            self.route_note.pack(fill='x',before=self.connection_fields,pady=(0,12))
        self.base_url_group.pack_forget()
        self.custom_name_group.pack_forget()
        if not preset.docs:
            self.base_url_group.pack(fill='x')
            self.custom_name_group.pack(fill='x',before=self.connection_fields)
        self.show_provider_group(preset.group)
        self.workspace_group.pack_forget()
        if '{workspace}' in route.url:
            self.workspace_group.pack(fill='x',after=self.route_note)
        self.base_url_entry.configure(state='readonly' if '{workspace}' in route.url else 'normal',readonlybackground=self.base_url_entry.cget('bg'))

    def route_changed(self, *_):
        preset = get_preset(self.vars['preset'].get())
        route = get_route(preset.key, self.vars['route'].get())
        self.loaded_provider = None
        values = dict(name=preset.service, model=route.models[0] if route.models else '',
                      base_url=route_url(route,self.vars['workspace'].get().strip()),
                      auth='API Key 保存到配置文件', env_key=preset.env, token='',
                      reasoning=reasoning_label(preset.reasoning), catalog='',
                      context_window='1048576' if preset.key=='Kimi' else '')
        self.catalog_bytes = None
        for key, value in values.items():
            self.vars[key].set(value)
        self.preset_controls()
        self.auth_changed()
        self.mark_clean()

    def workspace_changed(self, *_):
        if self.loading_preset:
            return
        route = get_route(self.vars['preset'].get(),self.vars['route'].get())
        if '{workspace}' in route.url:
            self.vars['base_url'].set(route_url(route,self.vars['workspace'].get().strip()))
            self.vars['token'].set('')

    def open_provider_docs(self):
        url = get_preset(self.vars['preset'].get()).docs
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo('自定义服务', '请向你的服务商确认 Responses API 基础地址、模型名称和密钥。', parent=self.root)

    def open_key_help(self):
        from desktop_ui import show_key_help
        show_key_help(self)

    def open_key_console(self):
        preset = get_preset(self.vars['preset'].get())
        url = KEY_GUIDES.get(preset.key, preset.docs)
        if url:
            webbrowser.open(url)
        else:
            self.open_provider_docs()

    def auth_changed(self, *_):
        direct = self.vars['auth'].get() == 'API Key 保存到配置文件'
        self.token_entry.configure(state='normal' if direct else 'disabled')
        if direct:
            self.env_group.pack_forget()
            self.token_group.pack(fill='x', before=self.auth_note)
            self.auth_note.configure(text='由服务商提供，不是账号密码。不知道去哪找？点击“如何获取密钥”。')
        else:
            self.token_group.pack_forget()
            self.env_group.pack(fill='x', before=self.auth_note)
            self.auth_note.configure(text='需提前设置系统环境变量。')
        if not direct:
            self.vars['token'].set('')

    def focus_field(self, widget, page=0):
        if page == 3:
            self.set_advanced(True)
        self.tabs.select(page)
        self.root.update_idletasks()
        _, canvas, content = self.tabs.pages[page]
        offset = widget.winfo_rooty() - content.winfo_rooty() - 55
        canvas.yview_moveto(max(0, offset) / max(1, content.winfo_height()))
        widget.focus_set()

    def paste_key(self):
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            self.show_error(ConfigError('剪贴板里没有文字。请先在服务商网站复制 API Key。'))
            return
        if not value or any(c.isspace() for c in value):
            self.show_error(ConfigError('请只复制完整的 API Key，不要包含说明文字或换行。'))
            return
        self.vars['token'].set(value)
        self.token_entry.focus_set()
        self.status.set('密钥已粘贴并隐藏。请继续检查配置。')

    def choose_config(self):
        p = filedialog.askopenfilename(title='选择 config.toml', filetypes=[('TOML', '*.toml')])
        if p:
            self.vars['config'].set(p)

    def choose_catalog(self):
        p = filedialog.askopenfilename(title='选择 Codex 模型目录', filetypes=[('JSON', '*.json')])
        if p:
            self.catalog_bytes = None
            self.vars['catalog'].set(p)

    def catalog_changed(self, *_):
        # A manually edited or cleared path must take precedence over downloaded data.
        self.catalog_bytes = None

    def load_current(self):
        if not self.confirm_discard():
            return
        try:
            snap = read_snapshot(self.vars['config'].get())
            doc = parse_config(snap.raw)
            pid = str(doc.get('model_provider', ''))
            provider = doc.get('model_providers', {}).get(pid)
            if not isinstance(provider, dict):
                raise ConfigError('当前没有可载入的自定义 Provider；可直接选择预设。')
            preset, route, workspace = identify_preset(str(provider.get('base_url','')),str(doc.get('model','')))
            self.clear_edit()
            self.loaded_provider = (str(snap.path), pid, str(provider.get('base_url', '')).rstrip('/'))
            self.catalog_bytes = None
            self.loading_preset = True
            self.vars['preset'].set(preset.key)
            self.vars['route'].set(route.label)
            self.vars['workspace'].set(workspace)
            self.loading_preset = False
            self.preset_controls()
            for k, v in {'provider': pid, 'name': provider.get('name', pid), 'model': doc.get('model', ''),
                         'base_url': provider.get('base_url', ''), 'reasoning': reasoning_label(str(doc.get('model_reasoning_effort', ''))),
                         'env_key': provider.get('env_key', 'CUSTOM_MODEL_API_KEY'),
                         'catalog': doc.get('model_catalog_json', ''), 'token': '',
                         'context_window': doc.get('model_context_window', ''),
                         'auth': '环境变量（推荐）' if 'env_key' in provider else 'API Key 保存到配置文件'}.items():
                self.vars[k].set(str(v))
            self.auth_changed()
            self.status.set('当前配置已载入。旧密钥不会回填；如使用直接 Key 方式，需重新输入。')
            self.footer_note.set('已载入当前配置 · 待检查')
            self.mark_clean()
        except Exception as err:
            self.show_error(err)

    def preferred_provider(self):
        if self.loaded_provider:
            path, provider, url = self.loaded_provider
            if str(Path(self.vars['config'].get()).expanduser().resolve()) == path and check_url(self.vars['base_url'].get()) == url:
                return provider
        return ''

    def settings(self):
        v = {k: value.get().strip() for k, value in self.vars.items()}
        if self.editing_profile:
            edit_snap,item = self.editing_profile
            from profile_store import assert_state
            assert_state(edit_snap.path, self.editing_state)
            current = read_snapshot(v['config'])
            if current != edit_snap:
                raise ConfigError('配置已变化，请取消编辑并刷新方案后重试。')
            if (v['auth'] == '环境变量（推荐）' and check_url(v['base_url']) != item['url']
                    and v['env_key'] == parse_config(current.raw)['model_providers'][item['fields']['model_provider']].get('env_key')):
                raise ConfigError('服务地址已改变，请重新连接并填写新服务的密钥，不能沿用原环境变量。')
            if not v['token'] and v['auth'] != '环境变量（推荐）' and check_url(v['base_url']) == item['url']:
                provider = parse_config(current.raw).get('model_providers', {}).get(item['fields'].get('model_provider'), {})
                if provider.get('base_url', '').rstrip('/') == item['url']:
                    v['token'] = str(provider.get('experimental_bearer_token', ''))
        if '{workspace}' in get_route(v['preset'],v['route']).url and not v['base_url']:
            self.focus_field(self.workspace_entry)
            raise ConfigError('请先填写有效的百炼工作空间 ID，再填写该地域的 API Key。')
        for key, widget, message in (
                ('name', self.custom_name_entry, '请给这个模型填写一个名称，方便在“我的模型”中找到它。'),
                ('base_url', self.base_url_entry, '请填写服务商提供的 API 地址；不清楚时可选择上方的服务商预设。'),
                ('model', self.model_entry, '请选择一个模型，或粘贴服务商控制台中的完整模型名称。'),
                ('token' if v['auth'] != '环境变量（推荐）' else 'env_key',
                 self.token_entry if v['auth'] != '环境变量（推荐）' else self.env_entry,
                 '请填写 API Key。它是服务商提供的访问密钥，不是账号密码；可点击“获取密钥”。' if v['auth'] != '环境变量（推荐）' else '请填写已设置的环境变量名称。')):
            if not v[key]:
                target = self.advanced_url_entry if key == 'base_url' else self.advanced_name_entry if key == 'name' else widget
                advanced = key in ('base_url','name') and bool(get_preset(v['preset']).docs)
                self.focus_field(target if advanced else widget, 3 if advanced else 0)
                raise ConfigError(message)
        if v['context_window'] and (not v['context_window'].isascii() or not v['context_window'].isdigit()):
            raise ConfigError('上下文长度需为正整数，或留空使用模型默认值。')
        if get_preset(v['preset']).service == 'OpenRouter' and v['token'].startswith(('sk-ant-', 'AIza')):
            raise ConfigError('当前通过 OpenRouter 接入，请填写 OpenRouter API Key，不能使用 Anthropic 或 Google 官方密钥。')
        return Settings(provider=suggested_provider_id(v['base_url']), name=v['name'], model=v['model'], base_url=v['base_url'],
                        auth_mode='env' if v['auth'] == '环境变量（推荐）' else 'token',
                        env_key=v['env_key'], token=v['token'], reasoning=REASONING_CHOICES.get(v['reasoning'], v['reasoning']),
                        catalog_path='' if self.catalog_bytes else v['catalog'], catalog_bytes=self.catalog_bytes,
                        context_window=int(v['context_window']) if v['context_window'] else None)

    def make_preview(self):
        if self.busy:
            self.status.set('正在处理，请稍候再检查。')
            return
        try:
            snap = read_snapshot(self.vars['config'].get())
            settings = self.settings()
            from provider_core import validate_settings
            validate_settings(settings)
            if self.vars['preset'].get() == 'DeepSeek' and not settings.catalog_path and not settings.catalog_bytes:
                self.fetch_catalog(continue_preview=True)
                return
            preferred = self.preferred_provider()
            editing = self.editing_profile
            expected = self.editing_state
            def work():
                from profile_store import resolve_choices, assert_state
                resolved = resolve_choices(snap)
                if editing:
                    assert_state(snap.path, expected)
                    if resolved[0] != expected or snap != editing[0]:
                        raise ConfigError('模型方案已被其他窗口修改，请刷新后重试。')
                provider = resolve_provider_id(snap, settings.base_url, preferred)
                plan = prepare(snap, replace(settings, provider=provider),
                               retired=editing[1]['id'] if editing else None, resolved=resolved)
                return provider, plan, resolved[1]
            self.background(work, lambda result: self.preview_ready(result, settings),
                            '正在检查配置和历史方案… 可以继续浏览，修改表单将取消本次检查。')
        except Exception as err:
            self.show_error(err)

    def preview_ready(self, result, settings):
        provider, self.plan, self.preview_choices = result
        self.vars['provider'].set(provider)
        self.preview_text.configure(state='normal')
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', self.plan.preview)
        self.preview_text.configure(state='disabled')
        self.save_button.configure(state='normal', text='保存并使用' if self.editing_profile else '备份并保存')
        self.preview_state.set('检查通过 · API Key 已隐藏 · 等待你确认保存')
        self.preview_summary.set(
            self.vars['name'].get() + '  /  ' + settings.model + '\n'
            + self.vars['route'].get() + '\n'
            + check_url(settings.base_url) + '\n\n'
            + ('密钥以明文保存到本机配置与备份。' if settings.auth_mode == 'token' else '密钥从系统环境变量读取。')
            + '\n保存会自动备份，并关闭内置联网搜索。\n保存后完全重启 Codex，新会话可读取模型名：' + settings.model + '\n实际连接与模型能力仍需测试。')
        self.tabs.select(1)
        self.status.set('检查通过。预览不写文件；点击“备份并保存”后才会写入。')

    def save(self):
        if self.busy or self.restart_running:
            self.status.set('请等待当前操作完成后再保存。')
            return
        if self.plan is None:
            return
        detail = '将备份并修改：\n' + str(self.plan.snapshot.path) + '\n\n保存后需完全重启 Codex，并新建会话。'
        if self.editing_profile:
            detail += '\n本次将更新原方案并立即选用，原方案不会重复留在列表中。'
        if self.vars['auth'].get() != '环境变量（推荐）':
            detail += '\nAPI Key 将明文保存在本机配置中。'
        try:
            before_doc = parse_config(self.plan.snapshot.raw)
            after_doc = parse_config(self.plan.updated)
            pid = after_doc['model_provider']
            old_provider = before_doc.get('model_providers', {}).get(pid, {})
            new_provider = after_doc['model_providers'][pid]
            if any(old_provider.get(k) != new_provider.get(k) for k in ('env_key', 'experimental_bearer_token')):
                affected = [p['label'] for p in self.preview_choices
                            if p['fields'].get('model_provider') == pid]
                if affected:
                    detail += '\n\n同一服务共用密钥，本次凭据修改也会影响：\n' + '\n'.join(affected)
        except Exception as err:
            self.show_error(err)
            return
        if not messagebox.askyesno('确认保存', detail, parent=self.root):
            return
        try:
            dest = apply_plan(self.plan)
            self.profile_config_changed()
            self.clear_edit()
            self.loaded_provider = (str(self.plan.snapshot.path), self.vars['provider'].get(), check_url(self.vars['base_url'].get()))
            self.invalidate()
            self.vars['token'].set('')
            self.mark_clean()
            self.status.set('已保存并校验。请重启 Codex。备份：' + str(dest))
            self.footer_note.set('已保存配置 · 请重启 Codex')
            self.refresh_backups()
            self.preview_state.set('配置已保存 · 下一步：重启 Codex 并新建会话')
            self.preview_summary.set('已保存：' + self.summary.get() + '\n原配置已备份。以后可在“我的模型”中再次使用，无需重新填写密钥。')
            self.success_panel.pack(fill='x', before=self.preview_card)
            self.tabs.select(1)
            self.tabs.pages[1][1].yview_moveto(0)
        except Exception as err:
            self.show_error(err)

    def refresh_backups(self):
        if self.busy:
            self.backup_pending = True
            return
        self.backup_pending = False
        requested = self.vars['config'].get()
        self.backup_rows = []
        self.render_backups()
        self.backup_state.set('正在读取备份… 可以继续浏览其他页面。')
        def work():
            from provider_core import backup_description
            from profile_store import read_state
            snap = read_snapshot(requested)
            state = read_state(snap.path)[0]
            return [(item, backup_description(snap, item, state=state)) for item in list_backups(snap.path)]
        def ready(rows):
            self.backup_rows = rows
            self.render_backups()
            if self.tabs.select() == 2:
                self.status.set('备份列表已更新。')
        self.background(work, ready, '正在读取本地备份…' if self.tabs.select() == 2 else self.status.get())

    def render_backups(self):
        rows = [(path, label) for path, label in self.backup_rows
                if not self.backup_filter.get() or label.startswith('可恢复')]
        self.backups = [path for path, _ in rows]
        self.backup_list.delete(0, 'end')
        for _, label in rows:
            self.backup_list.insert('end', label)
        self.restore_button.configure(state='disabled')
        self.backup_state.set(f'共 {len(self.backup_rows)} 个备份 · 当前显示 {len(rows)} 个 · 请选择版本'
                              if self.backup_rows else '暂无备份。第一次保存后会显示在这里。')

    def backup_selected(self, *_):
        selected = self.backup_list.curselection()
        label = self.backup_list.get(selected[0]) if selected else ''
        eligible = label.startswith('可恢复')
        self.restore_button.configure(state='normal' if eligible else 'disabled')
        self.backup_state.set('可恢复所选版本；确认后会先备份当前配置。' if eligible else
                             '此备份无法自动恢复：文件损坏或配置 / 模型列表已有后续改动。' if selected else '请选择一个备份。')

    def open_backup_folder(self):
        folder = Path(self.vars['config'].get()).expanduser().resolve().parent / 'provider-tool-backups'
        if not folder.is_dir():
            messagebox.showinfo('暂无备份', '第一次保存后会自动创建备份文件夹。', parent=self.root)
            return
        try:
            if sys.platform == 'win32':
                import os
                os.startfile(str(folder))
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', str(folder)])
            else:
                webbrowser.open(folder.as_uri())
        except OSError as err:
            self.show_error(err)

    def clear_edit(self):
        self.editing_profile = None
        self.editing_state = None
        if hasattr(self, 'model_heading'):
            self.model_heading.set('添加模型')
            self.model_next.configure(text='下一步  →')
        if hasattr(self, 'edit_banner'):
            self.edit_banner.pack_forget()

    def cancel_edit(self):
        if not self.confirm_discard():
            return
        self.clear_edit()
        self.preset_changed()
        self.invalidate()
        self.tabs.select(4)
        self.status.set('已取消编辑，配置未修改。')

    def editing_model_changed(self, *_):
        if self.editing_profile:
            _,item = self.editing_profile
            original = item['fields'].get('model_catalog_json', '')
            if self.vars['model'].get() != item['fields'].get('model') and self.vars['catalog'].get() == original:
                self.vars['catalog'].set('')
                self.catalog_bytes = None

    def edit_profile(self, choice_id, config_path):
        if self.profile_loading:
            return
        if self.busy or self.restart_running:
            self.status.set('请等待当前操作完成。')
            return
        requested = self.vars['config'].get()
        def work():
            from profile_store import resolve_choices
            snap = read_snapshot(requested)
            if str(snap.path) != config_path:
                raise ConfigError('配置文件路径已变更，请刷新方案列表。')
            resolved = resolve_choices(snap)
            item = next((p for p in resolved[1] if p['id'] == choice_id), None)
            if not item or choice_id == 'account':
                raise ConfigError('请选择一个自定义模型方案。')
            provider = parse_config(snap.raw).get('model_providers', {}).get(item['fields']['model_provider'], {})
            if provider.get('base_url', '').rstrip('/') != item['url']:
                raise ConfigError('服务地址已改变，请重新连接并填写新服务的密钥。')
            return snap, resolved[0], item, provider
        def ready(result):
            snap, state, item, provider = result
            if not self.confirm_discard():
                return
            fields = item['fields']
            self.vars['preset'].set('自定义 Responses 服务')
            self.preset_changed()
            self.loaded_provider = (str(snap.path), fields['model_provider'], item['url'])
            values = {'name':item['name'], 'model':fields['model'], 'base_url':item['url'],
                'reasoning':reasoning_label(str(fields.get('model_reasoning_effort', ''))),
                'context_window':fields.get('model_context_window', ''),
                'catalog':fields.get('model_catalog_json', ''), 'token':'',
                'env_key':provider.get('env_key', 'CUSTOM_MODEL_API_KEY'),
                'auth':'环境变量（推荐）' if 'env_key' in provider else 'API Key 保存到配置文件'}
            for key,value in values.items():self.vars[key].set(str(value))
            self.auth_changed()
            self.editing_profile = (snap,item)
            self.editing_state = state
            self.model_heading.set('编辑模型')
            self.model_next.configure(text='检查修改  →')
            self.edit_banner.pack(fill='x', before=self.provider_chooser, pady=(0,12))
            self.tabs.select(0)
            self.tabs.pages[0][1].yview_moveto(0)
            self.custom_name_entry.focus_set()
            self.status.set('正在编辑：' + item['label'])
            self.footer_note.set('编辑方案 · 保存并使用后生效')
            self.mark_clean()
        self.background(work, ready, '正在读取编辑方案… 可以继续浏览其他页面。')

    def delete_profile(self, choice_id, config_path):
        if self.profile_loading:
            return
        if self.busy or self.restart_running:
            self.status.set('请等待当前操作完成。')
            return
        requested = self.vars['config'].get()
        def work():
            from profile_store import resolve_choices
            snap = read_snapshot(requested)
            if str(snap.path) != config_path:
                raise ConfigError('配置文件路径已变更，请刷新方案列表。')
            resolved = resolve_choices(snap)
            item = next((p for p in resolved[1] if p['id'] == choice_id), None)
            if not item:raise ConfigError('方案已变化，请刷新列表。')
            if choice_id == 'account' or item['current']:
                raise ConfigError('当前使用中的方案和 ChatGPT套餐入口不能删除；请先切换其他方案。')
            return snap, resolved, item
        def ready(result):
            snap, resolved, item = result
            if not messagebox.askyesno('删除模型方案', '从“我的模型”删除：' + item['label'] + '\n\n不会切换当前模型。恢复备份和同服务共用的密钥会保留。', parent=self.root):return
            from profile_store import delete_choice
            delete_choice(snap, choice_id, resolved=resolved)
            if self.editing_profile and self.editing_profile[1]['id'] == choice_id:
                self.clear_edit()
            self.invalidate()
            self.refresh_profiles()
            self.status.set('方案已从列表删除，当前配置未修改。')
        self.background(work, ready, '正在检查待删除方案… 完成后将请你确认。')

    def refresh_profiles(self):
        self.profile_request += 1
        self.profile_pending = (self.profile_request, self.vars['config'].get())
        self.profile_loading = True
        self.selected_model.set('正在读取当前配置…')
        self.switch_state.set('正在读取模型方案… 可以继续使用其他页面。')
        from desktop_ui import set_profiles_loading
        set_profiles_loading(self, True)
        self.start_profile_worker()

    def profile_config_changed(self, *_):
        # Invalidate an outstanding read before its result can reach this UI.
        self.profile_request += 1
        self.profile_pending = None
        self.profile_choices = []
        from desktop_ui import render_profiles
        render_profiles(self, [], '')
        self.profile_loading = False
        self.selected_model.set('配置已更新，请重新读取方案')
        if self.tabs.select() == 4:
            self.refresh_profiles()

    def start_profile_worker(self):
        if self.profile_worker_running or self.profile_pending is None:
            return
        request, config_path = self.profile_pending
        self.profile_pending = None
        self.profile_worker_running = True
        def work():
            try:
                snap = read_snapshot(config_path)
                result = (str(snap.path), choices(snap, history_cache=self.profile_history_cache))
                self.profile_events.put((request, config_path, result, None))
            except Exception as err:
                self.profile_events.put((request, config_path, None, err))
        threading.Thread(target=work, daemon=True).start()

    def poll_profiles(self):
        try:
            request, config_path, result, error = self.profile_events.get_nowait()
        except queue.Empty:
            return
        self.profile_worker_running = False
        if request == self.profile_request and config_path == self.vars['config'].get():
            self.profile_loading = False
            from desktop_ui import render_profiles, set_profiles_loading
            if error is not None:
                from beginner_help import explain_error
                help = explain_error(error)
                self.profile_choices = []
                render_profiles(self, [], '')
                self.selected_model.set('无法读取配置，请检查配置文件位置')
                self.switch_state.set('读取失败 · ' + help.title + '：' + help.message)
                self.status.set('读取未完成。修正后点击“刷新方案”重试；可在“设置”检查配置位置。')
            else:
                path, self.profile_choices = result
                render_profiles(self, self.profile_choices, path)
                self.switch_state.set('已读取本机配置 · 共 ' + str(len(self.profile_choices)) + ' 个方案')
            set_profiles_loading(self, False)
        self.start_profile_worker()

    def switch_profile(self, choice_id, config_path):
        if self.profile_loading:
            return
        if self.busy:
            self.status.set('请等待当前操作完成后再切换。')
            return
        requested_path = self.vars['config'].get()
        auto_restart = self.auto_restart.get()
        def work():
            from switch_profiles import prepare_switch_review
            snap = read_snapshot(requested_path)
            if str(snap.path) != config_path:
                raise ConfigError('配置文件路径已变更，请刷新方案列表。')
            reset_url = choice_id == 'account' and bool(parse_config(snap.raw).get('openai_base_url'))
            plan, label = prepare_switch_review(snap, choice_id, reset_account_url=reset_url)
            target = discover_desktop(snap.path) if auto_restart else None
            return plan, label, target, reset_url
        def confirm(result):
            plan, label, target, reset_url = result
            if requested_path != self.vars['config'].get():
                raise ConfigError('配置文件路径已变更，请刷新方案列表。')
            detail = '切换到：' + label + '\n\n配置文件：' + str(plan.snapshot.path)
            detail += '\n\n会备份当前配置。'
            if target:
                detail += '\n保存成功后自动重启 ' + target.label + '。\n桌面应用的所有窗口都会关闭；请先完成或停止正在运行的任务。\n本工具无法判断任务是否结束。重新打开后请新建会话。'
            else:
                detail += '\n请完全重启 Codex，并新建会话。'
            if choice_id == 'account':
                detail += '\n使用 Codex 的 ChatGPT 登录。若原登录已失效，请在 Codex 中重新登录。'
                if reset_url:
                    detail += '\n\n检测到自定义 OpenAI 地址。本次将备份并移除该地址覆盖，恢复默认地址后切回套餐。'
            if not messagebox.askyesno('切换模型方案', detail, parent=self.root):
                self.status.set('已取消切换，配置未修改。')
                return
            dest = apply_plan(plan)
            self.clear_edit()
            self.invalidate()
            self.refresh_profiles()
            self.footer_note.set('已切换配置 · 请重启 Codex')
            self.status.set('已切换到 ' + label + '。请重启 Codex。备份：' + str(dest))
            if target:
                self.begin_restart(target)
            else:
                messagebox.showinfo('切换完成', '配置已切换。请完全重启 Codex，并新建会话。\n当前会话不会自动更换模型。', parent=self.root)
        self.background(work, confirm, '正在校验切换方案… 完成后将请你确认，可以继续浏览其他页面。')

    def restart_codex(self):
        if self.busy:
            self.status.set('请等待当前操作完成后再重启。')
            return
        try:
            target = discover_desktop(self.vars['config'].get())
            if messagebox.askyesno('重启 Codex', '将正常退出并重新打开 ' + target.label + '。\n桌面应用的所有窗口都会关闭；请先完成或停止正在运行的任务。\n本工具无法判断任务是否结束。继续？', parent=self.root):
                self.begin_restart(target)
        except Exception as err:
            self.show_error(err)

    def begin_restart(self, target):
        self.restart_running = True
        def work():
            try:
                return True, restart_desktop(target)
            except Exception as err:
                detail = str(err) if isinstance(err, ConfigError) else '系统未完成重启，请手动退出并重新打开 Codex。'
                return False, detail
        def done(result):
            self.restart_running = False
            success, detail = result
            self.footer_note.set('已重新打开 · 请新建会话' if success else '配置已保留 · 请手动重启')
            self.status.set(detail if success else '重启未完成；已保存的配置保持不变。' + detail)
            if success:
                messagebox.showinfo('重启完成', detail, parent=self.root)
            else:
                messagebox.showwarning('重启未完成', '已保存的配置保持不变。\n' + detail, parent=self.root)
        self.background(work, done, '正在正常退出并重新打开 Codex；若无法退出，将提示手动处理…', track_changes=False)

    def restore(self):
        if self.busy or self.restart_running:
            self.status.set('请等待当前操作完成后再恢复。')
            return
        selected = self.backup_list.curselection()
        if not selected:
            messagebox.showinfo('选择备份', '先刷新并选择一个备份。', parent=self.root)
            return
        item = self.backups[selected[0]]
        try:
            from provider_core import read_backup_manifest
            read_backup_manifest(item)
        except ConfigError as err:
            self.show_error(err)
            return
        if not messagebox.askyesno('恢复配置', '将恢复此备份前的配置，并再次备份当前文件。\n' + item.name, parent=self.root):
            return
        try:
            safety = restore_backup(Path(self.vars['config'].get()), item)
            self.clear_edit()
            self.profile_config_changed()
            self.invalidate()
            self.refresh_backups()
            self.status.set('已恢复。请重启 Codex。恢复前的配置备份：' + str(safety))
            self.footer_note.set('已恢复配置 · 请重启 Codex')
        except Exception as err:
            self.show_error(err)

    def background(self, fn, callback, label, track_changes=True):
        if self.busy:
            return
        self.busy = True
        self.background_cancelled = False
        revision = self.revision if track_changes else None
        self.fetch_button.configure(state='disabled')
        self.catalog_fetch_button.configure(state='disabled')
        self.test_button.configure(state='disabled')
        self.status.set(label)
        if track_changes and hasattr(self, 'cancel_background_button'):
            self.cancel_background_button.grid(row=0, column=3, padx=(6,0))
        def work():
            try:
                self.events.put((callback, fn(), None, revision))
            except Exception as err:
                self.events.put((callback, None, err, revision))
        threading.Thread(target=work, daemon=True).start()

    def cancel_background(self):
        if self.busy and not self.restart_running:
            self.revision += 1
            self.background_cancelled = True
            self.backup_pending = False
            if self.testing_revision is not None:
                self.connection_state.set('已取消等待，未应用测试结果')
            if self.backup_state.get().startswith('正在读取'):
                self.backup_state.set('已取消读取，点击“刷新列表”重试。')
            self.cancel_background_button.grid_remove()
            self.status.set('已取消应用本次结果；后台操作结束后即可重试，填写内容保留。')

    def poll(self):
        self.poll_profiles()
        try:
            callback, result, error, revision = self.events.get_nowait()
            self.busy = False
            if hasattr(self, 'cancel_background_button'):
                self.cancel_background_button.grid_remove()
            self.fetch_button.configure(state='normal')
            self.catalog_fetch_button.configure(state='normal')
            self.test_button.configure(state='normal')
            if getattr(self, 'background_cancelled', False):
                self.status.set('已取消本次操作，填写内容保留，可以重新检查。')
            elif revision is not None and revision != self.revision:
                if hasattr(self, 'backup_state') and self.backup_state.get().startswith('正在读取'):
                    self.backup_state.set('读取结果已过期，请点击“刷新列表”重试。')
                self.status.set('操作期间配置已变更，请按当前配置重新检查。')
            elif error:
                if self.testing_revision == self.revision:
                    self.connection_state.set('连接测试未通过')
                self.show_error(error)
            else:
                try:
                    callback(result)
                except Exception as err:
                    self.show_error(err)
            self.testing_revision = None
        except queue.Empty:
            pass
        if not self.busy and getattr(self, 'backup_pending', False):
            self.refresh_backups()
        if getattr(self, 'poll_after_id', None) is not None:
            self.root.after_cancel(self.poll_after_id)
        self.poll_after_id = self.root.after(100, self.poll)

    def fetch_catalog(self, continue_preview=False):
        revision = self.revision
        def received(data):
            if revision != self.revision:
                self.status.set('获取目录期间配置已变更，未应用返回结果。请重新获取。')
                return
            obj = validate_catalog(data)
            self.vars['catalog'].set('已获取官方目录，保存时写入配置目录')
            self.catalog_bytes = data
            self.status.set('官方目录已读取到内存，尚未写入。包含：' + ', '.join(m['slug'] for m in obj['models']))
            if continue_preview:
                self.make_preview()
        self.background(fetch_deepseek_catalog, received, '正在从 DeepSeek 官方文档获取目录；不会下载或执行安装脚本…')

    def test_api(self):
        if self.busy:
            return
        try:
            s = self.settings()
            from provider_core import validate_settings, check_url
            validate_settings(s)
            if not messagebox.askyesno('发送短消息测试', '向下列地址发送 API Key 和一条短测试消息，可能产生少量费用：\n' + check_url(s.base_url) + '/responses\n\n不会发送配置文件或工作区内容。继续？', parent=self.root):
                return
            def done(result):
                if self.testing_revision != self.revision:
                    self.status.set('测试期间配置已变更，结果不代表当前配置。请重新测试。')
                    return
                self.connection_state.set('文本请求已通过')
                self.status.set('短文本请求测试完成。客户端工具调用仍需单独验证。')
                messagebox.showinfo('接口测试结果', result, parent=self.root)
            self.testing_revision = self.revision
            self.connection_state.set('正在测试连接…')
            self.background(lambda: test_connection(s), done, '正在请求 Responses API，最长约 20 秒…')
        except Exception as err:
            self.show_error(err)

    def test_saved(self):
        """Read credentials only for the explicitly selected local configuration."""
        if self.busy:
            return
        try:
            snap = read_snapshot(self.vars['config'].get())
            doc = parse_config(snap.raw)
            from provider_core import validate_compatibility, validate_settings
            validate_compatibility(doc)
            pid = doc.get('model_provider', 'openai')
            if pid == 'openai':
                raise ConfigError('ChatGPT套餐请在 Codex 中新建会话验证；本工具不读取账号登录凭据。')
            pr = doc.get('model_providers', {}).get(pid, {})
            s = Settings(provider=pid, name=str(pr.get('name', pid)), model=str(doc.get('model', '')),
                         base_url=str(pr.get('base_url', '')), auth_mode='env' if pr.get('env_key') else 'token',
                         env_key=str(pr.get('env_key', '')), token=str(pr.get('experimental_bearer_token', '')))
            validate_settings(s)
            if pr.get('wire_api') != 'responses' or pr.get('requires_openai_auth') is not False:
                raise ConfigError('此服务不支持快速切换或测试，请重新配置。')
            if not messagebox.askyesno('测试已保存方案', '将测试配置中的模型：' + s.model + '\n目标地址：'
                                      + check_url(s.base_url) + '/responses\n\n使用本机已保存的密钥发送一条短消息，可能产生少量费用。继续？', parent=self.root):
                return
            if read_snapshot(snap.path) != snap:
                raise ConfigError('配置已被其他程序修改。请刷新后重试。')
            def done(result):
                if read_snapshot(snap.path) != snap:
                    self.status.set('测试期间已保存配置发生变化，结果不代表当前配置。')
                    return
                self.status.set('已保存方案的短文本测试完成；流式输出与工具调用仍需在 Codex 中验证。')
                messagebox.showinfo('已保存方案测试结果', result, parent=self.root)
            self.background(lambda: test_connection(s), done, '正在测试已保存方案，最长约 20 秒…')
        except Exception as err:
            self.show_error(err)

    def show_error(self, err):
        from beginner_help import explain_error
        help = explain_error(err)
        self.last_error_category = help.title
        if self.backup_state.get().startswith('正在读取'):
            self.backup_state.set('读取未完成，请检查配置位置后点击“刷新列表”重试。')
        msg = help.message
        self.status.set(msg)
        self.error_action = help.action
        if help.action:
            self.error_action_button.configure(text=help.button, width=170)
            self.error_action_button.grid(row=0,column=1,padx=(8,0))
            msg += '\n\n关闭提示后，可点击底部“' + help.button + '”。'
        else:
            self.error_action_button.grid_remove()
        messagebox.showerror(help.title, msg, parent=self.root)

    def copy_diagnostics(self):
        # Only fixed application labels; never copy config, URLs, keys or exception text.
        detail = ('Codex Connect ' + VERSION + '\n系统：' + sys.platform + '\n页面：'
                  + self.page_title.get() + '\n最近错误：' + getattr(self, 'last_error_category', '无'))
        self.root.clipboard_clear()
        self.root.clipboard_append(detail)
        self.status.set('已复制诊断摘要（版本、系统、页面和错误类别），不包含配置或密钥。')

    def resolve_error(self):
        action = self.error_action
        self.error_action_button.grid_remove()
        if action == 'help':
            self.open_key_help()
        elif action == 'auth':
            self.vars['auth'].set('API Key 保存到配置文件')
            self.auth_changed()
            self.focus_field(self.token_entry)
        elif action in ('key','model','workspace'):
            widget = {'key':self.token_entry if self.vars['auth'].get() != '环境变量（推荐）' else self.env_entry,
                      'model':self.model_entry,'workspace':self.workspace_entry}[action]
            self.focus_field(widget)
        elif action in ('name','url'):
            advanced = bool(get_preset(self.vars['preset'].get()).docs)
            widget = (self.advanced_name_entry if advanced else self.custom_name_entry) if action == 'name' else (self.advanced_url_entry if advanced else self.base_url_entry)
            self.focus_field(widget, 3 if advanced else 0)
        elif action in ('settings','catalog','context'):
            widget={'settings':self.advanced_config_entry,'catalog':self.advanced_catalog_entry,'context':self.advanced_context_entry}[action]
            self.focus_field(widget, 3)
        elif action == 'preview':
            self.make_preview()
        elif action == 'backups':
            self.tabs.select(2)
            self.refresh_backups()
        elif action == 'welcome':
            self.tabs.select(5)


def main():
    parser = argparse.ArgumentParser(description='Codex 模型配置助手')
    parser.add_argument('--config', help='配置文件路径，默认为 CODEX_HOME/config.toml')
    parser.add_argument('--smoke-ui', action='store_true', help='用临时目录启动界面并自动退出，不访问真实配置')
    args = parser.parse_args()
    scratch = tempfile.TemporaryDirectory() if args.smoke_ui else None
    root = tk.Tk()
    app = App(root, Path(scratch.name) / 'config.toml' if scratch else args.config)
    if args.smoke_ui:
        root.after(1000, root.destroy)
    root.mainloop()
    if scratch:
        scratch.cleanup()


if __name__ == '__main__':
    main()
