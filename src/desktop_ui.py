"""Implementation of the approved v0.3 desktop design, without web services."""
import sys
import copy
import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox
from pathlib import Path
import webbrowser
from desktop_widgets import Surface, Button, ProviderTile, SlimScroll, rounded
from desktop_widgets import BG, PAPER, TEXT, MUTED, LINE, ACCENT, SOFT, INPUT, NAV, CONTROL_LINE, ON_ACCENT
from provider_presets import PRESETS

FAMILY = 'Microsoft YaHei UI' if sys.platform == 'win32' else 'PingFang SC'


def text(parent, value='', size=9, color=TEXT, bold=False, **kwargs):
    return tk.Label(parent, text=value, bg=parent.cget('bg'), fg=color,
                    font=(FAMILY, size, 'bold' if bold else 'normal'), bd=0, **kwargs)


def note(parent, value='', **kwargs):
    obj = text(parent, value, color=MUTED, anchor='w', justify='left', **kwargs)
    def resize(event):
        width = max(100, event.width)
        if getattr(obj, '_wrap_width', None) != width:
            obj._wrap_width = width
            obj.configure(wraplength=width)
    obj.bind('<Configure>', resize)
    return obj


def icon(parent, kind='connect', color=ACCENT, bg=None, size=24):
    c = tk.Canvas(parent, width=size, height=size, bg=bg or parent.cget('bg'), bd=0, highlightthickness=0)
    if kind == 'connect':
        c.create_arc(2,6,16,18, start=90, extent=180, style='arc', outline=color, width=2)
        c.create_arc(9,6,23,18, start=-90, extent=180, style='arc', outline=color, width=2)
        c.create_line(8,12,17,12, fill=color, width=2)
    elif kind == 'shield':
        c.create_polygon(12,2,3,6,4,15,12,22,20,15,21,6, fill='', outline=color, width=1.5)
        c.create_line(7,11,11,15,17,8, fill=color, width=1.5)
    else:
        for y, x in ((6,9),(12,16),(18,11)):
            c.create_line(3,y,21,y, fill=color, width=1)
            c.create_oval(x-2,y-2,x+2,y+2,fill=c.cget('bg'),outline=color)
    return c


def card(parent, title, tag=None):
    shell = Surface(parent, radius=15, padding=15)
    shell.pack(fill='x', pady=(0, 14))
    head = tk.Frame(shell.inner, bg=PAPER)
    head.pack(fill='x', pady=(0, 10))
    text(head, '' if isinstance(title,tk.Variable) else title, 10, bold=True,
         **({'textvariable':title} if isinstance(title,tk.Variable) else {})).pack(side='left')
    if tag:
        text(head, tag, 8, MUTED, padx=6, pady=2).pack(side='right')
    return shell.inner


def field(parent, app, title, key, hint='', values=None, **kwargs):
    group = tk.Frame(parent, bg=parent.cget('bg'))
    group.pack(fill='x', pady=(0, 8))
    text(group, title, 9, MUTED).pack(anchor='w', pady=(0, 5))
    box = Surface(group, color=INPUT, border=CONTROL_LINE, radius=8, padding=13)
    box.pack(fill='x')
    if values is None:
        entry = tk.Entry(box.inner, textvariable=app.vars[key], bg=INPUT, fg=TEXT,
                         insertbackground=ACCENT, bd=0, highlightthickness=0,
                         disabledbackground=INPUT, disabledforeground=MUTED,
                         selectbackground=SOFT, selectforeground=TEXT,
                         font=(FAMILY, 9), relief='flat', **kwargs)
    else:
        entry = ttk.Combobox(box.inner, textvariable=app.vars[key], values=values,
                             state='readonly', style='Flat.TCombobox')
    entry.pack(fill='x', padx=3)
    entry.bind('<FocusIn>', lambda e: box.focus_border(True))
    entry.bind('<FocusOut>', lambda e: box.focus_border(False))
    if hint:
        note(group, hint, size=8).pack(fill='x', pady=(7, 0))
    return entry, group


class Pages:
    def __init__(self, parent, app):
        self.parent, self.app = parent, app
        self.pages, self.buttons, self.footers = {}, {}, {}
        self.active = 0

    def add(self, num):
        page = tk.Frame(self.parent, bg=BG)
        page.grid(row=0, column=0, sticky='nsew')
        footer = tk.Frame(page, bg=PAPER, padx=27, pady=15)
        footer.pack(side='bottom', fill='x')
        tk.Frame(page, bg=LINE, height=1).pack(side='bottom', fill='x')
        viewport = tk.Frame(page, bg=BG)
        viewport.pack(fill='both', expand=True, padx=(27, 18), pady=(24, 17))
        canvas = tk.Canvas(viewport, bg=BG, bd=0, highlightthickness=0)
        bar = SlimScroll(viewport, canvas.yview)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = tk.Frame(canvas, bg=BG)
        window = canvas.create_window(0, 0, window=content, anchor='nw')
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        self.pages[num] = (page, canvas, content)
        self.footers[num] = footer
        return content

    def select(self, number=None):
        if number is None:
            return self.active
        self.active = number
        for key, (page, _, _) in self.pages.items():
            if key == number:
                page.grid()
            else:
                page.grid_remove()
        self.pages[number][0].tkraise()
        for key, btn in self.buttons.items():
            btn.set_selected(key == number)
        self.app.page_title.set({0:'编辑模型' if self.app.editing_profile else '添加模型',3:'设置',1:'确认配置',2:'备份管理',4:'我的模型',5:'开始使用'}[number])
        if number == 4:
            self.app.refresh_profiles()
        if number == 2:
            self.app.refresh_backups()

    def wheel(self, event):
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Combobox)):
            return
        frame, canvas, _ = self.pages[self.active]
        bounds = canvas.bbox('all')
        if bounds and str(event.widget).startswith(str(frame)) and bounds[3] > canvas.winfo_height():
            delta = (-1 if event.num == 4 else 1) if getattr(event,'num',None) in (4,5) else (-int(event.delta/120) if abs(event.delta)>=120 else -int(event.delta))
            canvas.yview_scroll(delta,'units')


def heading(parent, title, subtitle, app, load=False):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill='x', pady=(0, 16))
    if load:
        Button(row,'↓  载入现有配置',app.load_current,height=44).pack(side='right',anchor='n',pady=4)
    words = tk.Frame(row,bg=BG); words.pack(side='left',fill='x',expand=True)
    text(words,'' if isinstance(title,tk.Variable) else title,20,bold=True,
         **({'textvariable':title} if isinstance(title,tk.Variable) else {})).pack(anchor='w')
    note(words,subtitle,size=9).pack(fill='x',pady=(6,0))


def build_ui(app, config_path, version, doc_url):
    root = app.root
    from app_icon import PNG
    app.window_icon = tk.PhotoImage(data=PNG)
    root.iconphoto(True, app.window_icon)
    root.configure(bg=BG)
    root.geometry(f'{min(1100, root.winfo_screenwidth()-60)}x{min(760, root.winfo_screenheight()-100)}')
    root.minsize(min(860, root.winfo_screenwidth()-60), min(580, root.winfo_screenheight()-100))
    for name in ('TkDefaultFont','TkTextFont','TkMenuFont'):
        tkfont.nametofont(name).configure(family=FAMILY,size=9)
    style = ttk.Style(root); style.theme_use('clam')
    root.option_add('*TCombobox*Listbox.background', INPUT)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', SOFT)
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT)
    root.option_add('*TCombobox*Listbox.font', (FAMILY, 9))
    style.configure('Flat.TCombobox',padding=0,fieldbackground=INPUT,background=INPUT,foreground=TEXT,borderwidth=0,arrowcolor=MUTED,font=(FAMILY,9))
    style.map('Flat.TCombobox',fieldbackground=[('readonly',INPUT)],selectbackground=[('readonly',INPUT)],selectforeground=[('readonly',TEXT)],foreground=[('disabled',MUTED),('readonly',TEXT)])
    style.layout('Flat.TCombobox',[('Combobox.padding',{'sticky':'nswe','children':[('Combobox.downarrow',{'side':'right','sticky':'ns'}),('Combobox.textarea',{'sticky':'nswe'})]})])
    app.vars = {key:tk.StringVar() for key in ('config','preset','provider','name','model','base_url','auth','env_key','token','reasoning','catalog','route','workspace','context_window')}
    app.vars['config'].set(str(config_path)); app.vars['preset'].set('DeepSeek')
    for key,value in {'page_title':'添加模型','status':'','summary':'',
                      'preview_state':'等待检查','backup_state':'点击刷新列表，查看本地备份。',
                      'catalog_status':'首次使用需获取目录','connection_state':'尚未测试连接',
                      'summary_name':'DeepSeek','summary_model':'deepseek-flash','summary_auth':'环境变量',
                      'summary_path':'','footer_note':'尚未保存任何改动'}.items():
        setattr(app,key,tk.StringVar(value=value))

    sidebar_width=max(190,tkfont.Font(family=FAMILY,size=10,weight='bold').measure('Codex Connect')+90)
    sidebar = tk.Frame(root,bg=NAV,width=sidebar_width)
    sidebar.pack(side='left',fill='y'); sidebar.pack_propagate(False)
    tk.Frame(root,bg=LINE,width=1).pack(side='left',fill='y')
    brand = tk.Frame(sidebar,bg=NAV); brand.pack(fill='x',padx=20,pady=(30,31))
    mark = Surface(brand,color=ACCENT,border=ACCENT,radius=10,padding=5)
    mark.pack(side='left',padx=(0,9)); icon(mark.inner,color=ON_ACCENT).pack()
    words = tk.Frame(brand,bg=NAV); words.pack(side='left')
    text(words,'Codex Connect',10,bold=True).pack(anchor='w')
    shell = tk.Frame(root,bg=BG); shell.pack(side='left',fill='both',expand=True)
    statusbar = tk.Frame(shell,bg=PAPER,padx=27,pady=5); statusbar.pack(side='bottom',fill='x')
    app.short_status = tk.StringVar()
    statusbar.columnconfigure(0,weight=1)
    status_label = text(statusbar,textvariable=app.short_status,size=8,color=MUTED,anchor='w',width=1)
    status_label.grid(row=0,column=0,sticky='ew')
    def shorten(*_):
        if hasattr(app,'error_action_button'):
            app.error_action_button.grid_remove()
        message=app.status.get().replace('\n',' ')
        app.short_status.set(message[:80]+('…' if len(message)>80 else ''))
        if message:
            statusbar.pack(side='bottom',fill='x',before=body)
        else:
            statusbar.pack_forget()
    app.status.trace_add('write',shorten)
    Button(statusbar,'详情',lambda:messagebox.showinfo('操作状态',app.status.get(),parent=root),kind='ghost',height=44,width=42,font=(FAMILY,8)).grid(row=0,column=2)
    app.error_action = ''
    app.error_action_button=Button(statusbar,'',app.resolve_error,height=44,width=170,font=(FAMILY,8))
    app.cancel_background_button=Button(statusbar,'取消等待',app.cancel_background,height=44,width=84,font=(FAMILY,8))
    body = tk.Frame(shell,bg=BG); body.pack(fill='both',expand=True)
    shorten()
    body.rowconfigure(0,weight=1); body.columnconfigure(0,weight=1)
    app.tabs=Pages(body,app)
    for num,title in [(0,'＋   添加模型'),(4,'⇄   我的模型'),(3,'☷   设置')]:
        btn=Button(sidebar,title,lambda n=num:app.start_add_model() if n==0 and (app.tabs.select()!=0 or app.editing_profile) else app.tabs.select(n),kind='nav',height=44,font=(FAMILY,10))
        btn.pack(fill='x',padx=14,pady=2); app.tabs.buttons[num]=btn
    credits=tk.Frame(sidebar,bg=NAV)
    credits.pack(side='bottom',fill='x',padx=20,pady=24)
    qr_path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets/author-qr.png'
    app.author_thumbnail=tk.PhotoImage(file=str(qr_path)).subsample(3)
    app.author_button=tk.Button(credits,image=app.author_thumbnail,command=lambda:show_author(app),
                                bg=NAV,activebackground=NAV,bd=0,relief='flat',cursor='hand2',
                                highlightthickness=1,highlightbackground=NAV,highlightcolor=ACCENT,
                                padx=0,pady=0,takefocus=1)
    app.author_button.bind('<Return>',lambda event:app.author_button.invoke())
    app.author_button.pack(anchor='w',pady=(0,10))
    note(credits,'CodexConnect  ·  v'+version,size=8,width=1).pack(fill='x')

    main=app.tabs.add(0)
    app.model_heading=tk.StringVar(value='添加模型')
    heading(main,app.model_heading,'选择服务 → 填写访问密钥 → 确认并保存',app)
    app.edit_banner=tk.Frame(main,bg=SOFT)
    note(app.edit_banner,'编辑方案 · 密钥留空可保留原密钥；修改地址后须重新填写。',size=9).pack(side='left',padx=12,pady=10)
    Button(app.edit_banner,'取消编辑',app.cancel_edit,kind='ghost',width=90,height=40).pack(side='right')
    chooser=card(main,'服务商')
    app.provider_chooser=chooser.master
    groups=tk.Frame(chooser,bg=PAPER);groups.pack(fill='x',pady=(0,10))
    providers=tk.Frame(chooser,bg=PAPER); providers.pack(fill='x')
    for index in range(4): providers.columnconfigure(index,weight=1,uniform='providers')
    app.provider_tiles=[]
    app.provider_group_buttons={}
    provider_font=tkfont.Font(family=FAMILY,size=9,weight='bold')
    provider_minimum=max(160,max(provider_font.measure(p.title) for p in PRESETS if p.docs)+85)
    provider_layout=None
    def show_group(group):
        nonlocal provider_layout
        app.visible_provider_group=group
        columns=max(1,min(4,providers.winfo_width()//provider_minimum)) if providers.winfo_width()>1 else 4
        if provider_layout == (group,columns):
            return
        provider_layout=(group,columns)
        if group == '自定义模型':
            providers.pack_forget()
            groups.pack_configure(pady=0)
        else:
            providers.pack(fill='x')
            groups.pack_configure(pady=(0,10))
        for column in range(4):providers.columnconfigure(column,weight=1 if column<columns else 0,minsize=0,uniform='providers' if column<columns else '')
        visible=0
        for tile in app.provider_tiles:
            tile.grid_forget()
            if tile.preset_group==group:
                tile.grid(row=visible//columns,column=visible%columns,sticky='ew',padx=(0,8) if visible%columns<columns-1 else 0)
                visible+=1
        for label,button in app.provider_group_buttons.items(): button.set_selected(label==group)
    app.show_provider_group=show_group
    def select_group(group):
        members=[p.key for p in PRESETS if p.group==group]
        remembered=app.last_group_presets.get(group)
        target=remembered if remembered in members else members[0]
        # Confirm before changing either the visible tab or the form.
        if not choose(target):
            return
        if group == '自定义模型':
            app.tabs.pages[0][1].yview_moveto(0)
            app.custom_name_entry.focus_set()
    for group in ('自定义模型','国内模型','国际模型'):
        button=Button(groups,group,lambda g=group:select_group(g),kind='segment',height=44,font=(FAMILY,9))
        button.pack(side='left',padx=(0,8));app.provider_group_buttons[group]=button
    def choose(name):
        accepted=app.choose_preset(name)
        show_group(get_preset_group(app.vars['preset'].get()))
        return accepted
    def get_preset_group(key):
        return next(p.group for p in PRESETS if p.key==key)
    for preset in PRESETS:
        if preset.group == '自定义模型':
            continue
        tile=ProviderTile(providers,preset.title,'经 OpenRouter' if preset.service=='OpenRouter' else ('手动填写' if not preset.docs else '官方服务'),
                          preset.symbol,lambda n=preset.key:choose(n),FAMILY,width=150)
        tile.preset_key=preset.key;tile.preset_group=preset.group
        app.provider_tiles.append(tile)
    show_group('国内模型')
    def resize_providers(event):
        if getattr(app,'provider_width',None)!=event.width:
            app.provider_width=event.width
            show_group(app.visible_provider_group)
    providers.bind('<Configure>',resize_providers)
    connection=card(main,app.summary_name)
    app.route_entry,app.route_group=field(connection,app,'套餐 / 地域','route',values=())
    app.route_selection=tk.StringVar(value=app.vars['route'].get())
    app.route_entry.configure(textvariable=app.route_selection)
    app.route_entry.bind('<<ComboboxSelected>>',app.choose_route)
    app.route_note=note(connection,'',size=9);app.route_note.pack(fill='x',pady=(0,12))
    app.workspace_entry,app.workspace_group=field(connection,app,'百炼工作空间 ID','workspace')
    app.custom_name_entry,app.custom_name_group=field(connection,app,'名称','name','例如：日常编程、工作专用。在“我的模型”中显示。')
    fields=tk.Frame(connection,bg=PAPER);fields.pack(fill='x')
    app.connection_fields=fields
    fields.columnconfigure(0,weight=2,uniform='entry');fields.columnconfigure(1,weight=3,uniform='entry')
    service=tk.Frame(fields,bg=PAPER);service.grid(row=0,column=0,sticky='nsew',padx=(0,20))
    auth=tk.Frame(fields,bg=PAPER);auth.grid(row=0,column=1,sticky='nsew')
    field_font=tkfont.Font(family=FAMILY,size=9)
    fields_minimum=max(540,field_font.measure('访问密钥（API Key）')*2+210)
    def arrange_fields(event):
        narrow=event.width<fields_minimum
        if getattr(app,'fields_narrow',None)==narrow:return
        app.fields_narrow=narrow
        service.grid_configure(row=0,column=0,columnspan=2 if narrow else 1,padx=0 if narrow else (0,20))
        auth.grid_configure(row=1 if narrow else 0,column=0 if narrow else 1,columnspan=2 if narrow else 1)
    fields.bind('<Configure>',arrange_fields)
    app.model_entry,app.model_group=field(service,app,'模型','model',values=())
    app.model_entry.configure(state='normal')
    app.base_url_entry,app.base_url_group=field(service,app,'服务地址','base_url')
    app.env_entry,app.env_group=field(auth,app,'环境变量名','env_key')
    app.token_entry,app.token_group=field(auth,app,'访问密钥（API Key）','token',show='•')
    key_actions=tk.Frame(app.token_group,bg=PAPER);key_actions.pack(fill='x',pady=(4,0))
    app.paste_button=Button(key_actions,'粘贴',app.paste_key,kind='ghost',height=44,font=(FAMILY,9))
    app.paste_button.pack(side='left')
    app.key_help_button=Button(key_actions,'如何获取密钥？',app.open_key_help,kind='ghost',height=44,font=(FAMILY,9))
    app.key_help_button.pack(side='left')
    app.auth_note=note(auth,'',size=8);app.auth_note.pack(fill='x')
    footer=app.tabs.footers[0]
    app.model_next=Button(footer,'下一步  →',app.make_preview,kind='primary',height=44)
    app.model_next.pack(side='right')
    app.test_button=Button(footer,'测试连接',app.test_api,height=44)
    app.test_button.pack(side='right',padx=(0,10))
    note(footer,textvariable=app.connection_state,size=9,width=1).pack(side='left',fill='x',expand=True)

    advanced=app.tabs.add(3)
    heading(advanced,'设置','通常保持默认即可。',app)
    shortcuts=tk.Frame(advanced,bg=BG);shortcuts.pack(fill='x',pady=(0,16))
    for num,label in ((2,'恢复备份'),(1,'查看待保存配置')):
        button=Button(shortcuts,label,lambda n=num:app.tabs.select(n),height=44)
        button.pack(side='left',padx=(0,10));app.tabs.buttons[num]=button
    common=card(advanced,'使用帮助')
    note(common,'不需要修改配置文件，也不需要编写代码。选择服务、填写访问密钥即可开始。').pack(fill='x',pady=(0,10))
    common_actions=tk.Frame(common,bg=PAPER);common_actions.pack(fill='x')
    app.guide_button=Button(common_actions,'查看使用引导',lambda:app.tabs.select(5),height=44)
    app.guide_button.pack(side='left')
    Button(common_actions,'如何获取密钥？',app.open_key_help,height=44).pack(side='left',padx=10)
    Button(common_actions,'载入当前模型',app.load_current,height=44).pack(side='left')
    Button(common_actions,'复制诊断摘要',app.copy_diagnostics,height=44).pack(side='left',padx=8)
    note(common,'载入不会修改配置；旧密钥不会回填。',size=8).pack(fill='x',pady=(8,0))
    app.manual_button=Button(common,'PDF 使用说明 ↗',app.open_manual,kind='ghost',height=44)
    app.manual_button.pack(anchor='w',pady=(6,0))
    app.advanced_content=tk.Frame(advanced,bg=BG)
    def set_advanced(expanded):
        if expanded:
            app.advanced_content.pack(fill='x',after=app.advanced_toggle)
        else:
            app.advanced_content.pack_forget()
        app.advanced_toggle.configure(text='收起高级设置 ↑' if expanded else '高级设置（通常不需要） ↓')
    app.set_advanced=set_advanced
    app.advanced_toggle=Button(advanced,'高级设置（通常不需要） ↓',lambda:set_advanced(not bool(app.advanced_content.winfo_manager())),kind='ghost',height=44)
    app.advanced_toggle.pack(anchor='w',pady=(0,12))
    access=card(app.advanced_content,'密钥方式')
    app.auth_buttons=[]
    def choose_auth(mode):
        app.vars['auth'].set(mode);app.auth_changed();app.sync_summary()
    row=tk.Frame(access,bg=PAPER);row.pack(fill='x')
    for title,value in [('环境变量','环境变量（推荐）'),('填写访问密钥','API Key 保存到配置文件')]:
        button=Button(row,title,lambda v=value:choose_auth(v),kind='segment',height=44)
        button.pack(side='right',padx=(10,0));app.auth_buttons.append(button)
    note(access,'环境变量需要提前设置；从 Finder 启动时可能无法读取终端变量。',size=9).pack(fill='x',pady=(10,0))
    location=card(app.advanced_content,'模型与配置')
    app.advanced_url_entry,_=field(location,app,'API 基础地址','base_url','预设已自动填写。通常无需修改；百炼地址由首页的工作空间 ID 生成。')
    app.advanced_config_entry,_=field(location,app,'配置文件位置','config','Codex 保存设置的文件。通常保持默认；只有使用其他配置目录时才需要更改。')
    actions=tk.Frame(location,bg=PAPER);actions.pack(fill='x',pady=(0,15))
    Button(actions,'选择配置文件',app.choose_config,height=44).pack(side='left')
    Button(actions,'载入当前模型',app.load_current,height=44).pack(side='left',padx=9)
    text(actions,'旧密钥不会回填',8,MUTED).pack(side='left')
    app.advanced_context_entry,_=field(location,app,'上下文长度 · 可选','context_window','可留空使用模型默认值；Kimi K3 预设填写官方建议值，切换服务时会重置。')
    two=tk.Frame(location,bg=PAPER);two.pack(fill='x')
    two.columnconfigure(0,weight=1,uniform='options');two.columnconfigure(1,weight=1,uniform='options')
    for i,title,key in [(0,'服务标识 · 自动生成','provider'),(1,'显示名称','name')]:
        group=tk.Frame(two,bg=PAPER);group.grid(row=0,column=i,sticky='ew',padx=(0,8) if i==0 else (8,0))
        control,_=field(group,app,title,key,'供 Codex 区分服务；无需填写，预览时自动检查重名。' if i==0 else '给这项服务起一个易认的名字，不影响模型调用。')
        if i==0:
            control.configure(state='readonly',readonlybackground=INPUT)
            app.provider_entry=control
        else:
            app.advanced_name_entry=control
    from app import REASONING_CHOICES
    field(location,app,'思考程度 · 可选','reasoning','不确定就选“自动”。较高可能更慢，并非每个模型都支持所有级别。',values=list(REASONING_CHOICES))
    catalog=card(app.advanced_content,'模型清单')
    app.advanced_catalog_entry,_=field(catalog,app,'服务商模型清单 · 可选','catalog','有服务商清单可在此导入；没有时会自动准备名称同步所需的清单。')
    note(catalog,'保存后完全重启 Codex，新会话可读取具体模型名；无需编写文件。',size=8).pack(fill='x',pady=(0,10))
    ca=tk.Frame(catalog,bg=PAPER);ca.pack(fill='x')
    Button(ca,'选择文件',app.choose_catalog,height=44).pack(side='left')
    app.catalog_quick=tk.Frame(catalog,bg=PAPER)
    app.catalog_quick.pack(fill='x',pady=(10,0))
    app.catalog_fetch_button=Button(app.catalog_quick,'获取 DeepSeek 官方目录',app.fetch_catalog,height=44)
    app.catalog_fetch_button.pack(side='left',padx=8)
    app.fetch_button=app.catalog_fetch_button
    Button(ca,'官方指南 ↗',lambda:webbrowser.open(doc_url),kind='ghost',height=44).pack(side='left')
    footer=app.tabs.footers[3]
    text(footer,'保存时默认关闭内置搜索',8,MUTED).pack(side='left')
    Button(footer,'下一步  →',app.make_preview,kind='primary',height=44).pack(side='right')

    preview=app.tabs.add(1)
    heading(preview,'确认连接','保存前，请核对服务与计费方式。',app)
    app.success_panel=Surface(preview,color=SOFT,border=ACCENT,radius=12,padding=18)
    text(app.success_panel.inner,'✓ 配置已保存',14,ACCENT,True).pack(anchor='w')
    note(app.success_panel.inner,'完成当前任务后，重启 Codex 并新建会话。',size=9).pack(fill='x',pady=10)
    success_actions=tk.Frame(app.success_panel.inner,bg=SOFT);success_actions.pack(fill='x')
    Button(success_actions,'重启 Codex',app.restart_codex,kind='primary',height=44).pack(side='left')
    Button(success_actions,'查看已保存的模型',lambda:app.tabs.select(4),height=44).pack(side='left',padx=10)
    app.saved_test_button=Button(app.success_panel.inner,'测试已保存方案',app.test_saved,height=44)
    app.saved_test_button.pack(anchor='w',pady=(10,0))
    pc=card(preview,'配置摘要','API Key 已隐藏')
    app.preview_card=pc.master
    note(pc,textvariable=app.preview_state,size=9).pack(fill='x',pady=(0,14))
    app.preview_summary=tk.StringVar(value='填写完成后点击“下一步”，这里会说明将使用哪个模型。')
    note(pc,textvariable=app.preview_summary,size=10).pack(fill='x',pady=(0,14))
    code=Surface(pc,color=INPUT,border=LINE,radius=12,padding=13)
    def toggle_code():
        if code.winfo_manager(): code.pack_forget();details_button.configure(text='查看技术详情（可选） ↓')
        else: code.pack(fill='both',expand=True,after=details_button);details_button.configure(text='收起技术详情 ↑')
    details_button=Button(pc,'查看技术详情（可选） ↓',toggle_code,kind='ghost',height=44,font=(FAMILY,9))
    details_button.pack(anchor='w')
    app.preview_details_button=details_button
    app.preview_text=tk.Text(code.inner,height=17,wrap='word',bg=INPUT,fg=TEXT,bd=0,highlightthickness=0,
                             font=('Consolas' if sys.platform=='win32' else 'Menlo',10),padx=5,pady=3,selectbackground=SOFT,selectforeground=TEXT)
    bar=SlimScroll(code.inner,app.preview_text.yview);bar.pack(side='right',fill='y')
    app.preview_text.configure(yscrollcommand=bar.set);app.preview_text.pack(fill='both',expand=True)
    app.preview_text.insert('1.0','# 尚未生成预览\n\n填写模型信息后，点击“下一步”。\n预览不写文件，密钥会自动隐藏。')
    app.preview_text.configure(state='disabled')
    footer=app.tabs.footers[1]
    app.save_button=Button(footer,'备份并保存',app.save,kind='primary',height=44,state='disabled')
    app.save_button.pack(side='right')
    Button(footer,'返回修改',lambda:app.tabs.select(0),height=44).pack(side='right',padx=(0,10))
    note(footer,'保存后重启 Codex，在新会话中验证',size=8,width=1).pack(side='left',fill='x',expand=True)

    backup=app.tabs.add(2)
    heading(backup,'恢复备份','每次保存都会自动备份。',app)
    bc=card(backup,'本地备份')
    note(bc,textvariable=app.backup_state,size=9).pack(fill='x',pady=(0,15))
    listing=Surface(bc,color=INPUT,radius=10,padding=12);listing.pack(fill='both',expand=True)
    app.backup_list=tk.Listbox(listing.inner,height=14,bd=0,highlightthickness=0,bg=INPUT,fg=TEXT,
                               font=(FAMILY,10),selectbackground=SOFT,selectforeground=ACCENT,activestyle='dotbox',exportselection=False)
    bar=SlimScroll(listing.inner,app.backup_list.yview);bar.pack(side='right',fill='y')
    app.backup_list.configure(yscrollcommand=bar.set);app.backup_list.pack(fill='both',expand=True)
    app.backup_list.bind('<<ListboxSelect>>',app.backup_selected)
    app.backup_filter=tk.BooleanVar(value=False)
    tk.Checkbutton(bc,text='只显示可恢复的备份',variable=app.backup_filter,command=app.render_backups,
                   bg=PAPER,fg=TEXT,activebackground=PAPER,selectcolor=PAPER,font=(FAMILY,9),
                   highlightthickness=0).pack(anchor='w',pady=(8,0))
    note(bc,'配置有后续改动时，自动恢复会停止，以保护这些改动。',size=8).pack(fill='x',pady=(13,0))
    footer=app.tabs.footers[2]
    Button(footer,'刷新列表',app.refresh_backups,height=44).pack(side='left')
    Button(footer,'打开备份文件夹',app.open_backup_folder,height=44).pack(side='left',padx=8)
    app.restore_button=Button(footer,'恢复所选版本…',app.restore,height=44,state='disabled')
    app.restore_button.pack(side='right')
    switch=app.tabs.add(4)
    heading(switch,'我的模型','切换已保存的模型，或返回 ChatGPT套餐。',app)
    app.selected_model=tk.StringVar(value='尚未读取配置')
    selection=Surface(switch,color=SOFT,border=ACCENT,radius=12,padding=18)
    selection.pack(fill='x',pady=(0,14))
    text(selection.inner,'配置已选择',9,ACCENT,True).pack(anchor='w')
    note(selection.inner,textvariable=app.selected_model,size=12,bold=True).pack(fill='x',pady=(6,8))
    note(selection.inner,'Codex 实际运行：尚未核实。保存配置不代表当前会话已切换。',size=9).pack(fill='x')
    note(selection.inner,'切换后请重启 Codex 并新建会话；左下角账号不能代表当前使用的模型。',size=9).pack(fill='x',pady=(4,0))
    app.switch_state=tk.StringVar(value='打开本页时读取本机方案。')
    note(switch,textvariable=app.switch_state,size=9).pack(fill='x',pady=(0,14))
    options=tk.Frame(switch,bg=BG);options.pack(fill='x',pady=(0,16))
    app.auto_restart=tk.BooleanVar(value=False)
    tk.Checkbutton(options,text='切换后自动重启 Codex',variable=app.auto_restart,
                   bg=BG,activebackground=BG,activeforeground=TEXT,fg=TEXT,selectcolor=PAPER,
                   font=(FAMILY,10),anchor='w').pack(fill='x')
    search=tk.Frame(switch,bg=BG); search.pack(fill='x',pady=(0,12))
    text(search,'搜索模型 / 服务商',9).pack(side='left',padx=(0,12))
    app.profile_search=tk.StringVar(value='')
    app.profile_search_entry=tk.Entry(search,textvariable=app.profile_search,font=(FAMILY,10),
                                      bg=PAPER,fg=TEXT,insertbackground=TEXT)
    app.profile_search_entry.pack(side='left',fill='x',expand=True,ipady=7)
    Button(search,'清除',lambda:app.profile_search.set(''),kind='ghost',width=64,height=40).pack(side='right')
    app.profile_search_entry.bind('<Escape>',lambda e:app.profile_search.set(''))
    app.profile_search.trace_add('write',lambda *_:render_profiles(app,app.profile_choices,getattr(app,'profile_config_path',''),page=0))
    app.profile_container=tk.Frame(switch,bg=BG)
    app.profile_pager=tk.Frame(switch,bg=BG)
    app.profile_page_label=tk.StringVar(value='')
    note(app.profile_pager,textvariable=app.profile_page_label,size=9).pack(side='left')
    app.profile_next=Button(app.profile_pager,'下一页',lambda:change_profile_page(app,1),height=40)
    app.profile_next.pack(side='right')
    app.profile_previous=Button(app.profile_pager,'上一页',lambda:change_profile_page(app,-1),height=40)
    app.profile_previous.pack(side='right',padx=(0,10))
    app.profile_container.pack(fill='x')
    def switch_help():
        messagebox.showinfo('切换说明','切换服务后需重启 Codex 并新建会话。请先完成或停止正在运行的任务。\n\nChatGPT 登录由 Codex 管理。同一服务共用当前密钥；确认保存后方案独立保存在本机，清理配置备份不再移除已登记的方案。旧方案会在首次确认保存时导入。',parent=root)
    Button(switch,'切换说明',switch_help,kind='ghost',height=44).pack(anchor='w')
    footer=app.tabs.footers[4]
    Button(footer,'刷新方案',app.refresh_profiles,height=44).pack(side='left')
    Button(footer,'重启 Codex',app.restart_codex,height=44).pack(side='left',padx=(10,0))
    app.add_model_button=Button(footer,'添加模型',app.start_add_model,kind='primary',height=44)
    app.add_model_button.pack(side='right')
    welcome=app.tabs.add(5)
    heading(welcome,'开始使用 Codex','不用写代码，也不用手动修改文件。先选择你的使用方式。',app)
    account=card(welcome,'使用 ChatGPT套餐')
    note(account,'在 Codex 中登录 ChatGPT，使用套餐内的 Codex 权益，无需填写访问密钥。\n如果之前切换过其他服务，可在“我的模型”中切回套餐。').pack(fill='x',pady=(0,12))
    app.welcome_account=Button(account,'使用 ChatGPT套餐',lambda:app.finish_welcome(4),height=44)
    app.welcome_account.pack(anchor='w')
    third=card(welcome,'连接其他模型')
    note(third,'1. 选择你使用的服务，模型和地址会预先填好。\n2. 按帮助获取访问密钥，回来点击“粘贴”。\n3. 测试连接，再确认保存。测试可能产生少量费用。').pack(fill='x',pady=(0,12))
    app.welcome_start=Button(third,'开始配置模型',lambda:app.finish_welcome(0),kind='primary',height=44)
    app.welcome_start.pack(anchor='w')
    note(welcome,'请先安装 Codex。保存后需要重启 Codex，并新建会话；本工具会自动备份原配置。',size=9).pack(fill='x')
    Button(app.tabs.footers[5],'我已熟悉，直接添加模型',lambda:app.finish_welcome(0),kind='ghost',height=44).pack(side='right')
    app.tabs.select(0)
    root.bind_all('<MouseWheel>',app.tabs.wheel,add='+')
    root.bind_all('<Button-4>',app.tabs.wheel,add='+')
    root.bind_all('<Button-5>',app.tabs.wheel,add='+')
    def reveal_focus(event):
        _, canvas, content=app.tabs.pages[app.tabs.active]
        widget=event.widget
        if str(widget).startswith(str(content)) and widget.winfo_ismapped():
            top=widget.winfo_rooty()-content.winfo_rooty()
            view_top=canvas.canvasy(0)
            if top<view_top or top+widget.winfo_height()>view_top+canvas.winfo_height():
                canvas.yview_moveto(max(0,top-25)/max(1,content.winfo_height()))
    root.bind_all('<FocusIn>',reveal_focus,add='+')
    root.bind('<Control-Return>',lambda e:app.make_preview())
    if sys.platform=='darwin':root.bind('<Command-Return>',lambda e:app.make_preview())


def show_key_help(app):
    from beginner_help import key_help
    from provider_presets import get_preset, get_route, KEY_GUIDES
    previous=getattr(app,'key_help_window',None)
    if previous is not None and previous.winfo_exists():
        previous.destroy()
    preset=get_preset(app.vars['preset'].get())
    route=get_route(preset.key,app.vars['route'].get())
    title,body=key_help(preset,route)
    window=tk.Toplevel(app.root)
    app.key_help_window=window
    window.title(title);window.configure(bg=BG)
    window.geometry('580x590');window.minsize(540,550)
    window.transient(app.root)
    window.grab_set()
    def close():
        window.grab_release();window.destroy()
        app.key_help_button.focus_set()
    window.protocol('WM_DELETE_WINDOW',close)
    window.bind('<Escape>',lambda e:close())
    actions=tk.Frame(window,bg=PAPER,padx=20,pady=14);actions.pack(side='bottom',fill='x')
    Button(actions,'我知道了，返回填写',close,height=44).pack(side='right')
    url=KEY_GUIDES.get(preset.key,preset.docs)
    if url:
        # Capture the selected provider; never derive a link from user input.
        app.key_console_button=Button(actions,'打开服务商页面 ↗',lambda:webbrowser.open(url),kind='primary',height=44)
        app.key_console_button.pack(side='left')
    else:
        app.key_console_button=None
    content=tk.Frame(window,bg=BG,padx=24,pady=24);content.pack(fill='both',expand=True)
    text(content,title,14,bold=True).pack(anchor='w',pady=(0,18))
    # Text wraps and scrolls at larger system font sizes; content is read-only.
    details=tk.Text(content,wrap='word',bg=BG,fg=TEXT,bd=0,highlightthickness=0,
                    font=(FAMILY,10),spacing1=3,spacing3=5,takefocus=1)
    bar=SlimScroll(content,details.yview);bar.pack(side='right',fill='y')
    details.configure(yscrollcommand=bar.set)
    details.pack(fill='both',expand=True)
    details.insert('1.0',body);details.configure(state='disabled')
    app.key_help_text=details
    details.focus_set()


def set_profiles_loading(app, loading):
    for name in ('switch_buttons','edit_buttons','delete_buttons'):
        for key, button in getattr(app,name,{}).items():
            current = any(item['id']==key and item['current'] for item in app.profile_choices)
            disabled = loading or (name != 'edit_buttons' and current)
            button.configure(state='disabled' if disabled else 'normal')
    page=getattr(app,'profile_page',0)
    count=max(1,(getattr(app,'profile_filtered_count',len(app.profile_choices))+5)//6)
    app.profile_previous.configure(state='disabled' if loading or page<=0 else 'normal')
    app.profile_next.configure(state='disabled' if loading or page>=count-1 else 'normal')


def change_profile_page(app, step):
    if app.profile_loading:
        return
    page=getattr(app,'profile_page',0)+step
    render_profiles(app,app.profile_choices,app.profile_config_path,page=page)
    app.tabs.pages[4][1].yview_moveto(0)


def render_profiles(app, profiles, config_path, page=None):
    # Always reread configuration upstream; reuse widgets only when display data matches.
    data=(config_path,profiles)
    previous=getattr(app,'_rendered_profiles',None)
    if page is None:
        page=getattr(app,'profile_page',0) if previous is not None and previous[:2]==data else 0
    query=app.profile_search.get().strip().casefold()
    matches=[item for item in profiles if query in item['label'].casefold() or query in item['url'].casefold()]
    app.profile_filtered_count=len(matches)
    page=max(0,min(page,max(0,(len(matches)-1)//6)))
    app.profile_page=page
    app.profile_config_path=config_path
    rendered = (config_path, profiles, page, query)
    selected=next((item for item in profiles if item['current']),None)
    app.selected_model.set('正在读取当前配置…' if app.profile_loading else
                           selected['label'] if selected else '未识别到可切换的模型配置')
    if getattr(app, '_rendered_profiles', None) == rendered:
        return
    app._rendered_profiles = None
    for child in app.profile_container.winfo_children():
        child.destroy()
    app.switch_buttons={}
    app.edit_buttons={}
    app.delete_buttons={}
    app.profile_cards={}
    if len(matches)>6:
        app.profile_pager.pack(fill='x',pady=(0,12),before=app.profile_container)
        app.profile_page_label.set(f'共 {len(matches)} 个 · 第 {page+1} / {(len(matches)+5)//6} 页')
    else:
        app.profile_pager.pack_forget()
    if not matches and query:
        note(app.profile_container,'没有找到匹配的模型。试试服务商名称，或点击“清除”查看全部。').pack(fill='x',pady=20)
    for item in sorted(matches,key=lambda item:not item['current'])[page*6:(page+1)*6]:
        account=item['id']=='account'
        chosen=item['current']
        surface=Surface(app.profile_container,color=SOFT if chosen else PAPER,
                        border=ACCENT if chosen else LINE,radius=16,padding=20)
        surface.pack(fill='x',pady=(0,14))
        app.profile_cards[item['id']]=surface
        panel=surface.inner
        row=tk.Frame(panel,bg=panel.cget('bg')); row.pack(fill='x')
        # Pack the fixed action first so long names wrap without hiding it.
        btn=Button(row,'✓ 已选择' if chosen else ('切回套餐' if account else '切换到此模型'),
                   lambda key=item['id']:app.switch_profile(key,config_path),
                   kind='selected' if chosen else 'normal',height=44,
                   state='disabled' if chosen else 'normal')
        if chosen:
            btn.configure(cursor='arrow',takefocus=0)
        btn.pack(side='right',padx=(15,0))
        details=tk.Frame(row,bg=panel.cget('bg'));details.pack(side='left',fill='x',expand=True)
        note(details,item['label'],size=10,bold=True,width=1).pack(fill='x')
        description='使用 ChatGPT 套餐内的 Codex 权益；无需 API Key' if account else item['url']+'\n同一服务的模型共用当前密钥'
        note(details,description,size=9,width=1).pack(fill='x',pady=(6,0))
        app.switch_buttons[item['id']]=btn
        if not account:
            actions=tk.Frame(panel,bg=panel.cget('bg'));actions.pack(fill='x',pady=(10,0))
            edit=Button(actions,'编辑',lambda key=item['id']:app.edit_profile(key,config_path),kind='ghost',width=72,height=36)
            edit.pack(side='right')
            delete=Button(actions,'删除',lambda key=item['id']:app.delete_profile(key,config_path),kind='ghost',width=72,height=36,state='disabled' if chosen else 'normal')
            delete.pack(side='right',padx=(0,6))
            if chosen:note(actions,'先切换到其他方案后可删除',size=8).pack(side='left')
            app.edit_buttons[item['id']]=edit
            app.delete_buttons[item['id']]=delete
    app._rendered_profiles = copy.deepcopy(rendered)
    set_profiles_loading(app,app.profile_loading)


def show_author(app):
    previous=getattr(app,'author_window',None)
    if previous is not None and previous.winfo_exists():
        previous.lift()
        return
    path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets/author-qr.png'
    try:
        photo=tk.PhotoImage(file=str(path))
    except (OSError,tk.TclError):
        messagebox.showerror('二维码无法显示','请重新下载完整应用后重试。',parent=app.root)
        return
    window=tk.Toplevel(app.root)
    app.author_window=window
    window.title('二维码')
    window.configure(bg=PAPER)
    window.resizable(False,False)
    window.transient(app.root)
    if window.winfo_screenheight()<650:
        photo=photo.subsample(2)
    window.qr_photo=photo
    text(window,'使用手机扫描下方二维码',10,MUTED).pack(padx=24,pady=(20,8))
    tk.Label(window,image=photo,bg=PAPER,bd=0).pack(padx=20)
    def close():
        window.destroy()
        app.author_button.focus_set()
    Button(window,'关闭',close,height=40,width=100).pack(pady=(8,20))
    window.protocol('WM_DELETE_WINDOW',close)
    window.bind('<Escape>',lambda e:close())
