"""Plain-language guidance. Never display arbitrary exception or server text."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorHelp:
    title: str
    message: str
    action: str = ''
    button: str = ''


def explain_error(err):
    from provider_core import ConfigError
    if isinstance(err, PermissionError):
        return ErrorHelp('无法访问这个位置', '当前文件或文件夹的权限不足。请检查所选配置位置及读写权限，然后重试。', 'settings', '检查配置位置')
    if not isinstance(err, ConfigError):
        return ErrorHelp('这一步没有完成', '请检查网络连接和文件夹权限后重试。如果仍然失败，请联系维护者协助处理；不要发送访问密钥。')
    msg = str(err)
    if msg.startswith('当前没有可载入'):
        return ErrorHelp('还没有配置其他模型', '你可以直接在 Codex 中使用 ChatGPT 账号，或通过使用引导添加其他模型。', 'welcome', '查看使用引导')
    if msg.startswith('HTTP '):
        code = msg.split('：', 1)[0]
        if code == 'HTTP 401':
            return ErrorHelp('访问密钥没有通过验证', '请重新复制当前服务的完整密钥。若密钥已删除或失效，请在服务商网站创建新的密钥。', 'key', '重新填写密钥')
        if code == 'HTTP 403':
            return ErrorHelp('当前账号无法使用这个模型', '可能尚未开通模型权限，或所选套餐、地域与密钥不匹配。请在服务商网站核对，再重新测试。', 'help', '查看密钥帮助')
        if code == 'HTTP 404':
            return ErrorHelp('没有找到可用的模型服务', '请核对模型名称和服务地址。自定义服务还需要支持 Codex 使用的 Responses 接口，可向服务商确认。', 'model', '检查模型设置')
        if code == 'HTTP 429':
            return ErrorHelp('服务暂时限制了请求', '可能请求过于频繁，或可用额度不足。请稍后重试，并在服务商网站查看额度。', 'help', '查看服务帮助')
        return ErrorHelp('服务暂时没有正常回复', '请稍后再试。若持续失败，请查看服务商的网站公告或联系其客服。')
    rules = (
        (('服务地址已改变',), ErrorHelp('这个模型需要重新连接', '服务地址与保存方案不一致。请在“添加模型”重新填写该服务的地址和访问密钥，避免误用其他服务的密钥。')),
        (('配置已变化，请取消编辑',), ErrorHelp('编辑中的配置已发生变化', '请先取消编辑，刷新“我的模型”后重新选择。当前填写内容仍保留，旧预览不能覆盖新配置。')),
        (('方案管理文件',), ErrorHelp('本机模型列表文件需要检查', '请保留 provider-tool-profiles.json 和备份，不要删除原配置。可在“设置”检查配置位置，或请维护者协助修复列表文件，再点击“刷新方案”。', 'settings', '检查配置位置')),
        (('模型方案已被其他窗口修改',), ErrorHelp('模型列表刚刚发生了变化', '此次操作已停止。请刷新“我的模型”后重新选择，避免覆盖其他窗口的改动。')),
        (('旧式 profile',), ErrorHelp('需要迁移旧版配置', '当前 Codex 已不支持旧式 profile。请保留备份，将设置迁移到独立的 profile-name.config.toml，并用 --profile 选择。可请维护者协助；本工具不会自动改写这些设置。', 'settings', '查看配置位置')),
        (('OpenAI 地址覆盖',), ErrorHelp('需要确认服务地址', '当前存在自定义 OpenAI 地址。请回到“我的模型”点击“切回套餐”，核对恢复默认地址的说明后再确认。')),
        (('ChatGPT套餐请在',), ErrorHelp('请在 Codex 中验证套餐', '使用 ChatGPT套餐时，请在 Codex 中新建会话验证。本工具不读取你的账号登录凭据。')),
        (('自动重启', '手动重启', '手动退出', '尚未完全退出', '未检测到桌面进程'),
         ErrorHelp('未能自动重新打开 Codex', '请先完成正在运行的任务，然后手动退出并重新打开 Codex，再新建会话。如果正在切换模型，可取消“切换后自动重启 Codex”，重新确认切换。')),
        (('方案已变化', '配置文件路径已变更'), ErrorHelp('模型列表需要刷新', '请回到“我的模型”点击“刷新方案”，再选择需要使用的模型。')),
        (('命名 profile', '覆盖了内置 OpenAI'), ErrorHelp('现有设置与账号切换冲突', '这次没有切换。请联系维护者检查 Codex 中已有的自定义设置，确认后再试；不要直接删除配置文件。')),
        (('服务配置已删除', '不支持快速切换'), ErrorHelp('这个模型需要重新连接', '请回到“添加模型”，选择对应服务并重新填写访问密钥，再确认保存。', 'model', '重新配置模型')),
        (('剪贴板', '只复制完整', '不含空白字符的 API Key', '请填写 API Key'),
         ErrorHelp('请填写访问密钥', '请在服务商网站复制完整的访问密钥，再点击“粘贴”。不要填写账号密码，也不要复制说明文字。', 'key', '填写访问密钥')),
        (('OpenRouter API Key',), ErrorHelp('需要使用 OpenRouter 的密钥', '这个模型通过 OpenRouter 接入。请获取 OpenRouter 的访问密钥；模型官网的密钥不能在这里使用。', 'help', '查看获取步骤')),
        (('请给这个模型填写',), ErrorHelp('请给模型起个名称', '填写一个方便自己识别的名称，例如“日常编程”。保存后会显示在“我的模型”里。', 'name', '填写名称')),
        (('模型 ID', '完整模型名称', '显示名称'), ErrorHelp('请核对模型名称', '选择列表中的模型，或复制服务商提供的完整模型名称，不要包含空格。', 'model', '选择模型')),
        (('工作空间',), ErrorHelp('还需要填写工作空间编号', '请从百炼控制台复制当前地域的工作空间编号，再填写同一地域的访问密钥。', 'workspace', '填写工作空间')),
        (('环境变量',), ErrorHelp('尚未找到可用的访问密钥', '如果你不熟悉系统设置，可以改用“填写访问密钥”，直接粘贴服务商提供的密钥。', 'auth', '改用填写密钥')),
        (('API 地址', 'Responses API 基础地址',), ErrorHelp('请核对服务地址', '请复制服务商提供的基础地址，通常以 https:// 开头。不要包含密码，也不要粘贴某一次请求的完整地址。', 'url', '检查服务地址')),
        (('网络、TLS',), ErrorHelp('暂时无法连接到服务', '请检查网络是否可用，核对服务地址后再测试。暂时无法确定是网络、服务还是返回内容的问题。', 'model', '检查连接设置')),
        (('Responses API 对象', 'Responses 对象'), ErrorHelp('尚未确认服务可用', '服务没有返回完整的预期回复。请检查模型与服务地址；自定义服务需向服务商确认支持 Codex 的 Responses 接口。', 'model', '检查模型设置')),
        (('官方目录', '官方页面结构', '模型目录', 'models', 'slug'), ErrorHelp('模型列表还没有准备好', '如果使用 DeepSeek，请重新获取模型列表。自定义列表需由服务商提供有效文件，不需要自己编写代码。', 'catalog', '检查模型列表')),
        (('上下文长度', '推理级别'), ErrorHelp('高级选项填写有误', '不确定时可将上下文长度留空，并把思考程度设为“自动”。', 'context', '检查高级设置')),
        (('配置已被其他程序修改',), ErrorHelp('配置刚刚发生了变化', '为避免覆盖其他改动，这次没有保存。请重新点击“下一步”检查最新配置，再确认保存。', 'preview', '重新检查配置')),
        (('锁文件',), ErrorHelp('配置暂时无法保存', '请先关闭其他配置助手，再重试。如果仍然失败，请联系维护者检查占用情况；不要自行删除配置文件。')),
        (('备份', '校验失败'), ErrorHelp('未能安全恢复或保存配置', '为保护已有设置，操作已停止。请先查看备份；如果配置有后续改动，请联系维护者协助处理，不要手动覆盖文件。', 'backups', '查看备份')),
        (('config.toml', 'TOML', '不是表', 'Provider', '服务条目'), ErrorHelp('现有配置需要检查', '所选配置无法被安全读取或合并。请确认配置位置；若文件曾被其他工具修改，可查看备份或联系维护者协助处理，无需自己修改代码。', 'settings', '检查配置位置')),
    )
    for fragments, help in rules:
        if any(fragment in msg for fragment in fragments):
            return help
    return ErrorHelp('这一步没有完成', '请核对填写的信息后重试。如果仍然失败，请联系维护者协助处理；不要发送访问密钥。')


def key_help(preset, route):
    if not preset.docs:
        return ('向服务商获取连接信息',
                '1. 向你使用的服务商获取访问密钥、模型名称和服务基础地址。\n\n'
                '2. 确认该服务支持 Codex 使用的 Responses 接口。只说“兼容 OpenAI”还不够。\n\n'
                '3. 回到这里，分别粘贴这些信息，再点击“测试连接”。测试可能产生少量费用。')
    return (f'获取 {preset.service} 访问密钥',
            f'当前选择：{preset.title} · {route.label}\n\n'
            '1. 打开下方服务商页面，登录或注册该服务的账号。\n\n'
            '2. 找到“密钥管理”或“API Keys”，创建并复制访问密钥。\n\n'
            f'请注意：{preset.credential}\n\n'
            '3. 回到本工具，点击“粘贴”，再点击“测试连接”。测试可能产生少量费用。\n\n'
            '访问密钥不是登录密码，请勿分享给他人。费用和可用额度以服务商页面为准。')
