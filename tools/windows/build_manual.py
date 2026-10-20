"""Build the embedded cross-platform PDF. Requires ReportLab and a CJK TrueType font."""
import argparse
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from provider_core import VERSION

parser = argparse.ArgumentParser()
parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/simsun.ttc'))
parser.add_argument('--output', type=Path, default=ROOT / 'src/assets/manual.pdf')
args = parser.parse_args()
pdfmetrics.registerFont(TTFont('Chinese', str(args.font), subfontIndex=0))
ink = colors.HexColor('#232737')
accent = colors.HexColor('#6555D9')
body = ParagraphStyle('body', fontName='Chinese', fontSize=11, leading=19, textColor=ink, wordWrap='CJK', spaceAfter=12)
title = ParagraphStyle('title', parent=body, fontSize=25, leading=34, spaceAfter=24, textColor=accent)
heading = ParagraphStyle('heading', parent=body, fontSize=15, leading=24, spaceBefore=14, spaceAfter=9)
small = ParagraphStyle('small', parent=body, fontSize=10, leading=17, textColor=colors.HexColor('#626B7D'))
story = []
def p(text, style=body):
    story.append(Paragraph(escape(text).replace('\n', '<br/>'), style))
def section(name, text):
    p(name, heading)
    p(text)
def page(name):
    if story:
        story.append(PageBreak())
    p(name, title)

page('开始使用 Codex Connect')
p('模型配置助手 · ' + VERSION + ' · 作者：夏谈AI', small)
section('选择对应的安装包',
        f'Windows：双击 CodexConnect-{VERSION}.exe。\nApple 芯片 Mac：使用 AppleSilicon.dmg。\nIntel Mac：使用 Intel.dmg。\nMac 打开 DMG 后，把 CodexConnect.app 拖入“应用程序”再打开。')
p('发行包内置运行环境，普通用户不需要安装 Python。请先安装 Codex。本工具只负责模型连接配置，不提供账号、模型额度或协议转换。')
section('第一次打开', '使用 ChatGPT套餐：进入“我的模型”，选择套餐入口。\n连接第三方模型：选择“开始配置模型”，按向导填写服务商、模型和访问密钥。')
section('平台验证说明', 'Windows 包需通过独立运行与隔离配置检查。Mac 包仅做结构、依赖和磁盘镜像静态检查，尚无 Mac 真机、签名或公证证据。若系统阻止打开，请核对来源并遵循系统提示，不要关闭系统安全保护。')
p('PDF 已内置，应用中打开“设置 → PDF 使用说明”即可查看。独立 PDF 同时随发行包提供。', small)

page('添加与测试模型')
section('1. 选择服务和模型', '首次切换国内 / 国际分组会选第一项；再次切回恢复本次打开期间上次选择的服务商。有未保存输入时先询问，取消保留原页签和内容。请核对套餐、地域、模型名称。自定义服务需填写名称、模型 ID 与基础地址；服务必须支持 Responses API。只有 Chat Completions 接口的服务不能直接使用。')
section('2. 填写访问密钥', '点击“如何获取密钥？”查看对应帮助，前往服务商页面创建 API Key，再回到工具点击“粘贴”。密钥不是账号密码。Claude / Gemini 的 OpenRouter 通道必须使用 OpenRouter 密钥。')
section('3. 测试与确认', '“测试连接”会先说明目标地址并请求确认，然后发送一条短消息，可能产生少量费用。“下一步”准备脱敏预览；DeepSeek 缺少清单时会从官方文档获取。点击“备份并保存”后才修改配置。')
section('4. 保存后继续', '可以点击“测试已保存方案”，使用本机保存的密钥测试，无需重新粘贴；仍会先确认目标和费用。完成当前任务后，完全重启 Codex 并新建会话验证。')
p('仅完成且包含有效文字的回复可通过测试。短文本通过不代表流式输出、工具调用或多轮会话已通过。预设不代表账号已开通模型。直接填写的密钥会以明文保存在本机配置和备份中，请勿分享这些文件。', small)

page('管理模型与切回套餐')
section('切换模型', '打开“我的模型”后会在后台读取方案，期间可以使用其他页面。可以按模型或服务商名称搜索，超过 6 个方案时用“上一页 / 下一页”查看。点击切换后会后台校验，确认后才保存；需要完全重启 Codex 并新建会话；“配置已选择”仅说明本机配置内容。')
section('编辑与新增', '点击模型卡片“编辑”，页标题变为“编辑模型”。读取与检查在后台进行，可取消等待。修改后点击“检查修改”，再“保存并使用”。同地址密钥留空可保留旧密钥；修改地址必须重新填写。点击“添加模型”会开始新的方案，未保存的修改会先询问是否放弃。取消切换地域会保留输入和预览；载入失败会保留原编辑。其他窗口修改模型列表时需刷新重选。')
section('共享密钥与删除', '同一服务的模型共用当前凭据。修改凭据时，确认框会列出受影响方案。删除只移除列表中的方案，保留恢复备份和共用凭据；当前模型需要先切换再删除。')
section('ChatGPT套餐', '套餐通过 Codex 的 ChatGPT 登录使用，本工具不读写登录缓存。若存在自定义 OpenAI 地址，切回时会明确说明将备份并恢复默认地址；取消确认不会改动配置。若存在内置 OpenAI Provider 的高级覆盖，请先核对配置。')
p('自动重启默认关闭。启用前请完成或停止正在运行的任务；启动进程成功不代表模型请求已验证。', small)

page('备份、设置与故障处理')
section('恢复备份', '打开“设置 → 恢复备份”。进入后自动刷新，可筛选可恢复条目、打开备份文件夹；不可恢复的版本会禁用恢复按钮。列表显示时间、操作类型与前后模型。恢复会同时处理配置和方案状态，恢复前也会生成备份；存在后续改动时会停止覆盖。')
p('确认保存后，方案独立保存在本机，清理旧配置备份不会移除已登记方案。旧版本历史会在首次确认写入时导入。不要删除模型清单目录；不要将配置、备份、方案管理文件发给别人。')
section('常见错误', '401：重新核对密钥。\n403：检查模型权限、地域和套餐。\n404：核对地址与模型，确认支持 Responses。\n429：稍后重试，并核对速率和额度。\n清单获取失败：重试或导入服务商提供的有效文件。')
section('配置冲突或旧版 profile', '发现其他程序修改配置时，重新检查后再保存，不能强制覆盖。旧式 profile 配置会在保存和切换前被拦截；请保留备份并请维护者协助迁移，本工具不会自动改写这些高级设置。')
section('配置位置', '默认使用 CODEX_HOME/config.toml，未设置 CODEX_HOME 时使用用户目录中的 .codex/config.toml。高级设置默认折叠；环境变量鉴权需要提前设置，Mac Finder 启动的应用未必继承终端环境变量。')

p('损坏的备份会单独标记，其他条目仍可查看；损坏条目不能恢复。模型列表读取失败时，请按提示检查配置位置、权限或列表文件，再刷新重试。', small)

page('获取帮助')
p('作者 · 夏谈AI', heading)
p('使用手机扫描下方二维码。可在“设置”复制诊断摘要，包含版本、系统、页面与错误类别，不含配置或密钥。反馈时可补充操作步骤和已遮盖密钥的错误截图。')
story.append(Spacer(1, 16))
story.append(Image(str(ROOT / 'src/assets/author-qr.png'), width=220, height=220))
story.append(Spacer(1, 22))
p('不要发送 API Key、config.toml、登录缓存或备份目录。遇到恢复冲突时，请保留原文件并联系维护者；不要自行删除配置文件。')
p('Codex Connect ' + VERSION + '\n使用说明 · 2026-10-19', small)

def frame(canvas, doc):
    width, height = A4
    canvas.setFont('Chinese', 9)
    canvas.setFillColor(accent)
    canvas.drawString(44, height-32, 'CODEX CONNECT / ' + VERSION)
    canvas.setStrokeColor(colors.HexColor('#E7E9F1'))
    canvas.line(44, 43, width-44, 43)
    canvas.setFillColor(colors.HexColor('#626B7D'))
    canvas.drawString(44, 28, '使用说明 · 夏谈AI')
    canvas.drawRightString(width-44, 28, str(doc.page) + ' / 5')

args.output.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(args.output), pagesize=A4, rightMargin=44, leftMargin=44,
                  topMargin=67, bottomMargin=60, title='Codex Connect ' + VERSION + ' 使用说明', author='夏谈AI').build(story, onFirstPage=frame, onLaterPages=frame)
print(args.output)
