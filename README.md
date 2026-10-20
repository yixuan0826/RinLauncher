# Rin Launcher

> **VIBE CODING 提示**：代码与文档由 AI 辅助生成，未经专业安全审计。提权（UAC）、
> 自启动等功能会接触系统，请自行评估风险后使用。

基于 **RinUI（PySide6 + QML）** 的 Windows 桌面启动台：常驻右下角的小窗负责「点一下
就用」，启动台编辑与设置各自独立成窗。当前版本 **1.1.2**，完整变更见
[更新日志](CHANGELOG.md)，历史发行见
[Releases](https://github.com/yixuan0826/RinLauncher/releases)。

## 功能

| | |
| --- | --- |
| 🪟 **常驻小窗** | 云母桌面挂件，固定右下角、沉底、不抢焦点 |
| 🧩 **槽位** | 双行面板（最多 10 格）+ 存储区；每格可设文件 / 命令 / 网址 / 按键 / UWP |
| 🎛 **系统控制** | 音量、Wi-Fi、移动热点；状态每 2 秒与系统同步 |
| 🚀 **开始菜单导入** | 搜索并批量添加 `.lnk`、UWP / WSA 应用与 WSL 发行版 |
| 🔄 **更新** | 稳定 / Pre-Release 双通道，镜像测速与离线 zip 安装 |
| 💾 **备份** | 手动备份永久保留；每 7 天自动备份，保留最近 8 份 |
| ⌨️ **按键模拟** | 录制或手动编辑，支持组合键与长按，兼容中日韩输入法 |
| 🎨 **图标** | Fluent / 随包 Lawnicons / 自定义图片 / 从 exe·dll·lnk 提取 |
| 🔐 **提权** | 条目级 UAC、提权前确认、任务计划管理员自启动 |

---

## 界面与操作

- **小窗**：标题条（编辑 / 更多）→ 双行面板 → 存储区 → 系统控制条。左键启动，
  右键可编辑 / 提权打开 / 再加一格；「更多」里能打开设置、重启、提权重启、隐藏与退出。
- **系统控制**：音量滑条可静音；Wi-Fi 开关会自动连回第一个标记「自动连接」的网络；
  热点固定为 `rinlauncher-hotspot` / `12345678`（WPA2），开热点前会自动打开 Wi-Fi。
- **设置**：通用（启动 / 热键 / 权限）、个性化（主题 / 强调色 / 材质 / 动画）、
  更新、备份、关于。左侧分类栏可折叠。
- **开始菜单导入**：编辑窗口标题栏或槽位编辑器里点「从开始菜单导入」，搜索后
  多选添加 `.lnk`、UWP / WSA 与 WSL 应用；传统快捷方式会自动带上参数并抽取图标。
- **托盘与热键**：托盘可显示 / 隐藏、打开编辑或设置、打开配置目录、重载、退出；
  默认热键 `Ctrl+Space`，编辑 / 设置窗口关闭时只收起自己。

## 快速开始

**下载**：从 Releases 下载 `RinLauncher.zip`，解压后运行 `RinLauncher.exe`。
数据保存在同级 `data/`（`config.yaml`、`launcher.log`、`icons/`、`backups/`）；
目录不可写时自动回退到 `%APPDATA%\RinLauncher`。

**源码运行**：

```bash
git clone https://github.com/yixuan0826/RinLauncher.git
cd RinLauncher
pip install -r requirements.txt
python -m rin_launcher.main
```

源码模式的数据目录是 `%APPDATA%\RinLauncher`。

**打包**：

```bash
pip install pyinstaller
pyinstaller build.spec          # 产物：dist/RinLauncher/
```

应急单文件：`$env:RIN_ONEFILE="1"; pyinstaller build.spec`（启动较慢）。

---

## 更新与备份

- **更新**：稳定版取 Latest，测试版取最新 Pre-Release；包名固定 `RinLauncher.zip`。
  下载完成后点「安装并重启」，脚本会等待进程退出、覆盖安装目录并保留 `data/`。
  设置里可切换 GitHub / ghfast / ghproxy 镜像并手动测速，测速完成后可自动切到
  最快的可用源（可关闭）；下载慢或离线时也可选择本地 `RinLauncher.zip` 安装。
  安装流程仅在打包版可用，源码模式只能检查、下载或打开下载目录。
- **备份**：手动备份不会被清理；自动备份每 7 天一次，保留最近 8 份。
  每次写盘前还会额外保留 10 份 `config.yaml.bak.*` 兜底。

## 配置

路径：`data/config.yaml`（源码模式为 `%APPDATA%\RinLauncher\config.yaml`）。
外部修改会自动重载（0.5 秒防抖）。

```yaml
version: 3
launcher:
  slots:
    - {kind: action, row: 0, label: 记事本, action: {type: file, target: notepad.exe}}
    - {kind: tool, row: 0, key: configFolder}
    - {kind: usb, row: 1, label: U 盘}
    - {kind: path, row: 1, label: D 盘, path: "D:\\"}
  storagePath: ""          # 空 = 用户主目录
settings:
  theme: system            # system | light | dark
  accentColorMode: system  # system | custom
  accentColor: "#0078d4"   # accentColorMode=custom 时生效
  material: tabbed         # tabbed | mica | none
  globalHotkey: "Ctrl+Space"
  startupMode: off         # off | normal | admin
  updateChannel: stable    # stable | prerelease
  updateMirror: github     # github | ghfast | ghproxy
  updateMirrorAuto: true   # 测速后自动选择最快镜像
```

槽位 `kind`：`action`（完整动作）/ `tool`（内置功能）/ `path`（路径）/ `usb`（自动检测）；
`row` 0 = 面板，1 = 存储区。内置功能 key：`launcherPage` `settings` `configFolder`
`configFile` `reload` `elevate` `hide` `quit`。旧版 `apps` / `tools` / `keymouse` 配置会在读取时自动迁移。

---

## 动作类型与按键

| 类型 | 字段 | 说明 |
| --- | --- | --- |
| `file` | target / arguments / working_dir / run_as | 路径或 PATH 里的程序名 |
| `cmd` | target + arguments | 交给 shell 执行 |
| `url` | target | 自动补 `https://`；自定义协议（如 `classisland://`）原样交给系统 |
| `uwp` | target | UWP / WSA 的 AUMID，经 `shell:AppsFolder` 启动 |
| `keyboard` | keyboard_steps | 按顺序回放按键 / 等待 |

按键步骤：`{type: key, key: "ctrl+c", action: click|press|release, duration: 0.1}`
或 `{type: wait, duration: 0.5}`；有 `vk` 时优先按虚拟键码回放。
中日韩输入法下可打印字符走 `WM_CHAR` 注入，组合键与功能键仍走虚拟键码。

**占位符**：`{appdir}` `{configdir}` `{homedir}` `{tempdir}` `{desktop}` `{documents}` `{downloads}`；
`~` 与环境变量（`%APPDATA%`）同样会展开。

**图标**：`ic_fluent_*`、`lawnicons:*`、`file:<路径>`、空串（占位）。
更多 Lawnicons：`python scripts/vendor_lawnicons.py --source <svg 目录>`。

---

## 开发

```
rin_launcher/   Python 后端（配置 / 动作 / 系统控制 / 更新 / 输入法）
qml/            三个窗口与组件（components / dialogs / pages）
RinUI/          内联的 RinUI（MIT，本地补丁见 RinUI/LOCAL_PATCHES.md）
tests/          pytest 回归
```

- 三个窗口各自使用独立 QML 引擎；编辑 / 设置窗口按需创建。
- 下拉用 `onActivated: function (index) {...}`；弹窗用 `dialogs/AppDialog.qml`。
- 检查：`ruff check rin_launcher tests` 与 `pytest -q`。

## 版本记录

- **1.1.2**：强调色不再被设置页重置，新增跟随系统模式；更新镜像可选并测速，
  支持离线 zip 安装；开始菜单可批量导入 `.lnk`、UWP / WSA 与 WSL；新增 `uwp`
  动作与自定义协议 URL；修复键盘回放卡死。详见 [CHANGELOG.md](CHANGELOG.md)。
- **1.1.1**：热点开关 `NoneType` 修复；Wi-Fi / 热点状态 2 秒同步；强调色跨窗口
  同步并持久化；图标对比度修正。
- **1.1.0**：编辑 / 设置拆分为独立窗口；设置改为可折叠分类栏；系统强调色提取；
  Release 说明 Markdown 渲染；输入法兼容。

更早版本见 [Releases](https://github.com/yixuan0826/RinLauncher/releases)。

## 已知限制

- 仅 Windows；非 Windows 上相关功能安全降级或直接提示失败。
- 自动更新与离线安装只在打包版可用；源码模式只能检查、下载或打开下载目录。
- 小窗固定沉底、高度为桌面可用高度的一半，被最大化窗口挡住属预期。
- 托盘不可用时，关掉编辑 / 设置窗口可能直接退出程序。
- UWP / WSL 条目使用类型占位图标；传统 `.lnk` 才会自动抽取程序图标。
- 目标程序以管理员运行时，非提权进程的按键注入会被 UIPI 拦下。
- 只读 `WM_KEYDOWN` 的程序（部分游戏）可能收不到 Unicode 注入的字符。

---

## 许可证与致谢

MIT（见 [`LICENSE`](LICENSE)）。[RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) 为 MIT；
[Lawnicons](https://github.com/LawnchairLauncher/lawnicons) 为 Apache-2.0（图标补过 `viewBox`，
见 `assets/icons/lawnicons/NOTICE`）；Fluent UI System Icons 为 MIT。
更多依赖与版本信息见「设置 → 关于与鸣谢」。
