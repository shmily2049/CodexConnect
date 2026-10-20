# CodexConnect

面向 Windows 和 macOS 的 Codex 模型配置助手。通过桌面表单添加第三方模型、管理模型方案，并切回 ChatGPT套餐，无需手动编辑配置文件。

当前版本：**0.10.13（Windows 已验证；macOS 仅静态验证）**。作者：夏谈AI。

## 功能

- 首次使用引导、密钥帮助、中文错误提示和折叠高级设置。
- 国内外服务预设及自定义模型；自动生成 Provider ID，支持自定义方案名称。
- 配置预览、保存前备份、恢复和并发修改检查。
- 我的模型：搜索、分页、切换、编辑、删除；独立保存方案元数据，清理旧备份不丢失已登记方案。
- 关闭或切换服务前保护未保存输入；恢复配置同时恢复方案状态，检查后续改动。
- 保存后直接测试已保存方案；修改共享凭据时列出受影响模型，仍需确认发送请求。
- 生成本地模型清单，让 Codex 新会话读取具体模型名称。
- 可选重启 Codex、内置 PDF 使用说明。

本工具配置的是 Responses API 接入，不提供 Chat Completions 协议转换。服务商预设和示例模型不代表已验证全部流式输出、工具调用或账号权限。切换配置后需重启 Codex 并新建会话。

## 使用

发行版内置运行环境，普通用户无需安装 Python，也无需克隆仓库。点击下方直链下载 0.10.13 安装包；Windows 下载后直接运行 EXE。源码仓库不再跟踪安装包，完整更新内容与附件见 [GitHub Releases](https://github.com/shmily2049/CodexConnect/releases/tag/v0.10.13)。

- [Windows EXE](https://github.com/shmily2049/CodexConnect/releases/download/v0.10.13/CodexConnect-0.10.13.exe)
- [Mac Apple 芯片 DMG](https://github.com/shmily2049/CodexConnect/releases/download/v0.10.13/CodexConnect-0.10.13-AppleSilicon.dmg)
- [Mac Intel 芯片 DMG](https://github.com/shmily2049/CodexConnect/releases/download/v0.10.13/CodexConnect-0.10.13-Intel.dmg)
- [PDF 使用说明](https://github.com/shmily2049/CodexConnect/releases/download/v0.10.13/CodexConnect-0.10.13-Manual.pdf)

PDF 使用说明随 Windows EXE 内置。macOS 的标准交付形式为 AppleSilicon / Intel 两种 DMG，内含 `CodexConnect.app` 和说明书；Mac 包仍没有真机运行、签名或公证证据。

密钥会保存在用户本机配置和备份中，界面预览做脱敏处理。连接测试仅在用户确认后发送请求，可能产生费用。编辑方案时，同地址密钥留空可保留原密钥；修改地址须重新提供密钥。

## 开发

需要带 Tcl/Tk 的 Python 3.11+。TOML 依赖已随源码放在 `src/vendor/`。从项目根目录执行：

```powershell
python -B src/app.py --smoke-ui
python -B src/app.py --config work/dev/config.toml
python -B -m unittest discover -s src/tests -v
```

开发和测试使用隔离配置，不使用个人 Codex 配置。界面截图检查需要 Pillow 和可用桌面环境：

```powershell
python -m pip install Pillow
python -B tools/windows/check_redesign.py
python -B tools/windows/check_v3_states.py
python -B tools/windows/check_profile_management_ui.py
```

可选的离线 Codex 模型列表集成检查（需自行提供 Codex CLI 路径）：

```powershell
python -B tools/windows/verify_codex_model_list.py --codex-exe <Codex-CLI路径>
```

该检查使用临时配置和本地不可用端点，不发送模型推理请求。

## Windows 构建

首次使用固定版本依赖获取脚本；它从 PyPI 获取指定版本并核对 SHA-256：

```powershell
python tools/windows/get_wheels.py
python tools/windows/build_windows.py --dist-dir work/build-artifacts/0.10.13/windows-dist
python tools/windows/package_release.py --input-exe work/build-artifacts/0.10.13/windows-dist/CodexConnect.exe
python tools/windows/check_windows_release.py
```

构建前确保 `src/assets/manual.pdf` 已更新。输出为 `release/CodexConnect-0.10.13/`，Windows 打包入口自动复制 EXE 和独立 PDF；完整跨平台交付再加入两个 DMG。`release/` 仅作为本地构建输出，发行文件上传到 GitHub Releases，不再提交到 Git；构建缓存、依赖下载和本地测试日志继续忽略。根目录的 `启动应用.cmd` 用于启动本地已构建的 EXE。

## macOS 构建说明

`tools/macos/` 包含运行时获取、应用打包、依赖检查和 DMG 脚本。运行时来源和版本记录在 `latest-release.json`，证书来源记录在 `certifi-source.json`。运行时归档和 certifi wheel 不随源码仓库提交，需按记录下载并校验。

`build_bundle.py` / `verify_bundles.py` 负责应用结构与静态检查。当前 `build_dmg.py` 使用 Windows + WSL Ubuntu-24.04 及本地 `work/linux-dmg/` 中的 HFS+/DMG 工具；这些内部工具未随仓库提供，因此该步骤不能在刚克隆的目录中直接运行。Mac 真机运行、签名和公证仍待补齐。

完整跨平台版本在 `release/CodexConnect-<版本>/` 保留四个文件：Windows EXE、两个 DMG 和独立 PDF。Mac 中间 ZIP、校验和、构建日志放在 `work/build-artifacts/<版本>/`。

## 目录

| 路径 | 用途 |
| --- | --- |
| `src/` | 应用源码、资源、第三方 TOML 库与单元测试 |
| `design/` | 原浅色设计基础、交互规范及历史设计参考 |
| `tools/windows/` | Windows 构建与回归检查 |
| `tools/macos/` | Mac 应用/DMG 构建与静态检查 |
| `release/` | 本地发行输出，不纳入 Git；安装包通过 GitHub Releases 下载 |
| `work/` | 本地构建与测试中间文件，不纳入 Git |

界面实现以 `src/desktop_ui.py` 为准；历史设计稿不代表当前全部行为。

## 已有验证记录

0.10.13：修复历史方案凭据跨地址引用、并发删除后旧编辑复活方案、载入失败丢失编辑上下文，以及取消地域切换丢失预览。编辑、预览、删除和备份读取在后台执行，重复历史扫描合并；提供取消等待、备份自动刷新与筛选、恢复状态提示及脱敏诊断摘要。专项回归：`python -B tools/windows/check_review_013_ui.py`。

本版通过 108 项核心测试、15 组 Windows GUI 回归和 5 项 Windows 独立包检查；两种 Mac DMG 通过静态校验，尚无 Mac 真机、签名或公证证据。验证记录位于 `work/fix-0.10.13/` 和 `work/build-artifacts/0.10.13/`。


0.10.12：切换国内 / 国际模型分组时，首次默认选第一项，再次进入恢复本次打开期间上次选择的服务商，并同步表单。未保存内容先确认；取消保留原分组、输入和预览，重复点击当前分组不会重置输入。分组选择不保存实际配置。专项回归：`python -B tools/windows/check_group_ui.py`。

本版通过 105 项核心测试、14 组 Windows GUI 回归和 5 项 Windows 独立包检查；两种 Mac DMG 通过静态校验，仍无 Mac 真机、签名或公证证据。验证记录位于 `work/fix-0.10.12/` 和 `work/build-artifacts/0.10.12/`。

0.10.11 修复编辑页点击“添加模型”仍替换原方案、切换确认前阻塞界面、未完成或无有效文字的 Responses 回复被误判成功、损坏备份中断列表四项问题。切换校验在后台执行，每次只读取一次方案集合，确认保存前仍检查配置与方案状态是否变化；搜索只过滤已读取的数据，不访问磁盘或网络。新增/编辑标题和按钮分开显示，模型加载错误提供具体处理方向。专项入口为 `python -B tools/windows/check_review_011_ui.py`，测试均使用隔离配置和模拟请求。

本版通过 105 项核心测试、13 组 Windows GUI 回归和 5 项 Windows 独立包检查；两种 Mac DMG 仅通过静态检查。120 份人工旧备份、41 个方案的压力测试中，切换点击约 2.54 ms 返回，后台准备确认约 2979 ms，最大界面心跳间隔约 46 ms；原审查中同步准备确认阻塞约 6748 ms。这些数字不代表真实配置或 API 性能。原始记录位于 `work/fix-0.10.11/`，发行校验及源码归档位于 `work/build-artifacts/0.10.11/`。

0.10.10 专门修复“我的模型”入口阻塞：配置和历史备份在单个后台线程读取，重复刷新合并为最新请求；校验过的备份只缓存不含凭据的方案元数据，仍逐次读取并校验原文件。列表每页显示 6 个方案，读取失败清除旧卡片，配置位置变更时丢弃旧结果。保存与切换继续使用实时配置校验。

在 120 份虚拟备份、41 个方案的压力测试中，点击处理从 2895 ms 降到 3 ms，首次列表就绪从 3477 ms 降到 1072 ms，再次进入约 282 ms；最大界面心跳间隔从 2895 ms 降到 36 ms。不是用户真实配置实测，也不代表 API 响应速度。可运行 `python tools/windows/profile_model_list.py --output work/performance/models-current` 复现。通过 101 项单元测试、12 组 GUI 检查和 5 项 Windows 独立包检查；Mac 仍只有静态包验证。

0.10.9 优化输入、服务切换和窗口缩放：合并摘要刷新、跳过无变化重绘、停止隐藏页布局、复用内容未变化的模型卡片。保存预览仍立即失效，模型列表仍重新读取配置，避免显示过期状态。离线性能基准可用 `python tools/windows/profile_ui.py --output work/performance/current` 复现；计时包含 Tk 绘制和 profiler 开销，受机器与窗口环境影响，不代表 API 响应时间。专项回归入口为 `python tools/windows/check_performance_ui.py`。

本机相同隔离配置、每项 20 次操作的中位耗时：输入 10.77 → 1.46 ms，服务切换 81.72 → 10.64 ms，窗口缩放 200.20 → 69.42 ms；页面切换 40.42 → 37.60 ms。原始记录位于 `work/performance/`。97 项单元测试、10 组 GUI 检查和 5 项 Windows 独立包检查通过；两种 Mac DMG 通过静态检查，仍未做真机运行、签名和公证。

0.10.8 修复账号地址覆盖、恢复方案状态、新增/编辑混淆、旧式 profile 校验和独立 PDF 打包；新增方案独立存储、未保存保护、备份标签与保存后测试。本版通过 97 项单元测试、9 组 Windows GUI 检查、4 项隔离 Codex model/list 检查和 5 项 Windows 独立包检查；两个 Mac 包通过依赖、权限、DMG 回读与文件内容静态检查。验证记录存于 `work/fix-0.10.8/` 和 `work/build-artifacts/0.10.8/`。所有配置检查使用隔离文件，未发起真实推理请求；Windows 运行结果和 Mac 静态包结果分别记录。

## 第三方资源

TOMLKit 的许可见 `src/vendor/tomlkit-0.13.3.dist-info/LICENSE`。Codex 模型清单模板及提示词的来源、基线和 Apache-2.0 许可见 `src/assets/codex-catalog-NOTICE.txt` 和 `src/assets/codex-LICENSE.txt`。

## 更新 PDF 手册

开发环境安装 ReportLab 后，可运行 `python tools/windows/build_manual.py`。默认使用 Windows 的 SimSun 字体；其他系统通过 `--font` 指定可嵌入的中文 TrueType 字体。生成后渲染检查，再构建应用，确保三个应用与独立 PDF 一致。
