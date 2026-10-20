"""Curated Responses routes. Reference examples checked 2026-10-19, not account entitlements."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Route:
    label: str
    url: str
    models: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    group: str
    symbol: str
    service: str
    env: str
    docs: str
    routes: tuple[Route, ...]
    credential: str
    reasoning: str = ''


PRESETS = (
    Preset('DeepSeek', 'DeepSeek', '国内模型', 'D', 'DeepSeek', 'DEEPSEEK_API_KEY',
           'https://api-docs.deepseek.com/quick_start/agent_integrations/codex/',
           (Route('官方 API', 'https://api.deepseek.com', ('deepseek-flash',), '直连官方服务；点击检查时自动获取模型清单，无需手动准备。'),),
           '使用 DeepSeek 开放平台的 API Key。', 'high'),
    Preset('自定义 Responses 服务', '自定义服务', '自定义模型', '≡', '我的模型服务', 'CUSTOM_MODEL_API_KEY',
           '', (Route('自定义 Responses 接口', '', (), '填写支持 Responses 的基础地址；仅兼容 Chat Completions 的接口不能直接使用。'),),
           '使用所填 API 地址对应服务的密钥。'),
    Preset('Kimi', 'Kimi', '国内模型', 'K', 'Kimi', 'KIMI_API_KEY',
           'https://platform.kimi.com/docs/guide/codex-kimi',
           (Route('国内开放平台', 'https://api.moonshot.cn/v1', ('kimi-k3',), '原生 Responses；国内平台的 Key 与国际平台不能混用。Kimi K3 自动配置 1M 上下文。'),),
           '使用 platform.kimi.com 开放平台 API Key，不是 Kimi 聊天会员凭据。'),
    Preset('通义千问', '通义千问', '国内模型', 'Q', '阿里云百炼', 'DASHSCOPE_API_KEY',
           'https://www.alibabacloud.com/help/en/model-studio/codex',
           (Route('北京 · 按量付费', 'https://{workspace}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1', ('qwen3.7-max',),
                  '按量付费，需填写百炼 Workspace ID；Key 必须属于所选地域。仅选支持 Responses 的模型。'),
            Route('新加坡 · 按量付费', 'https://{workspace}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1', ('qwen3.7-max',),
                  '新加坡地域，按量付费；不是 Coding Plan 套餐入口，套餐 Key 不能混用。')),
           '使用对应地域的百炼按量付费 API Key；本预设不消耗 Coding Plan 套餐额度。'),
    Preset('豆包 / 火山方舟', '豆包 / 方舟', '国内模型', '豆', '火山方舟', 'ARK_API_KEY',
           'https://console.volcengine.com/ark/region:cn-beijing/docs/integrate-third-party-tools',
           (Route('按量付费 API', 'https://ark.cn-beijing.volces.com/api/v3', ('doubao-seed-2-1-pro-260915',),
                  '按量计费，不消耗编程套餐额度。请先开通模型，也可填写自己的接入点 ID。'),
            Route('Coding Plan 套餐', 'https://ark.cn-beijing.volces.com/api/coding/v3', ('ark-code-latest',),
                  '使用 Coding Plan 专属 Key；ark-code-latest 使用套餐控制台选中的模型。'),
            Route('Agent Plan 套餐', 'https://ark.cn-beijing.volces.com/api/plan/v3', ('ark-code-latest',),
                  '使用 Agent Plan 专属 Key；请先确认已开通该套餐。')),
           '使用所选计费方式对应的火山方舟 API Key；按量与套餐不能混用。'),
    Preset('OpenAI API', 'OpenAI', '国际模型', 'O', 'OpenAI API', 'OPENAI_API_KEY',
           'https://developers.openai.com/api/docs/models/gpt-6.1-sol',
           (Route('官方 API · 独立计费', 'https://api.openai.com/v1', ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna'),
                  '使用 OpenAI API 额度，不使用 ChatGPT 订阅额度。使用 ChatGPT套餐请进入“我的模型 → ChatGPT套餐”。'),),
           '使用 OpenAI API Platform 的 API Key，不是 ChatGPT 登录令牌。'),
    Preset('Grok', 'Grok', '国际模型', 'G', 'xAI Grok', 'XAI_API_KEY',
           'https://docs.x.ai/developers/model-capabilities/text/comparison',
           (Route('官方 API', 'https://api.x.ai/v1', ('grok-4.6',), '官方 Responses 接口；模型权限和费用以 API 控制台为准。'),),
           '使用 xAI API Key，不是 X / Grok 网页订阅凭据。'),
    Preset('Claude · OpenRouter', 'Claude', '国际模型', 'C', 'OpenRouter', 'OPENROUTER_API_KEY',
           'https://openrouter.ai/blog/tutorials/codex-cli-openrouter/',
           (Route('经 OpenRouter 接入', 'https://openrouter.ai/api/v1', ('anthropic/claude-sonnet-4.6',),
                  '经 OpenRouter 转发和计费，请求会交给 OpenRouter 及其上游。使用 OpenRouter 密钥，不是 Anthropic 官方 Key。'),),
           '仅填写 OpenRouter API Key（通常以 sk-or- 开头）；不要填 Anthropic 官方密钥。'),
    Preset('Gemini · OpenRouter', 'Gemini', '国际模型', '✦', 'OpenRouter', 'OPENROUTER_API_KEY',
           'https://openrouter.ai/blog/tutorials/codex-cli-openrouter/',
           (Route('经 OpenRouter 接入', 'https://openrouter.ai/api/v1', ('google/gemini-3.1-pro-preview',),
                  '经 OpenRouter 转发和计费；预填模型为 Preview，可改为控制台提供的完整模型名称。不能使用 Google 官方 Key。'),),
           '仅填写 OpenRouter API Key（通常以 sk-or- 开头）；不要填 Google / Gemini 官方密钥。'),
)
BY_KEY = {p.key: p for p in PRESETS}

# Key creation instructions, separated from model and integration documentation.
KEY_GUIDES = {
    'DeepSeek': 'https://api-docs.deepseek.com/',
    '通义千问': 'https://help.aliyun.com/zh/model-studio/get-api-key/',
    'OpenAI API': 'https://developers.openai.com/api/docs/quickstart',
    'Grok': 'https://docs.x.ai/developers/quickstart',
}


def get_preset(key):
    return BY_KEY.get(key, BY_KEY['自定义 Responses 服务'])


def get_route(key, label):
    preset = get_preset(key)
    return next((r for r in preset.routes if r.label == label), preset.routes[0])


def route_url(route, workspace=''):
    if '{workspace}' not in route.url:
        return route.url
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,62}', workspace):
        return ''
    return route.url.replace('{workspace}', workspace)


def identify_preset(url, model):
    url = url.rstrip('/')
    for preset in PRESETS:
        for route in preset.routes:
            if not route.url:
                continue
            pattern = re.escape(route.url).replace(re.escape('{workspace}'), r'([A-Za-z0-9][A-Za-z0-9-]{0,62})')
            match = re.fullmatch(pattern, url)
            if match:
                if preset.service == 'OpenRouter' and not model.startswith(route.models[0].split('/')[0] + '/'):
                    continue
                return preset, route, match.group(1) if match.groups() else ''
    preset = get_preset('自定义 Responses 服务')
    return preset, preset.routes[0], ''
