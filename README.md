# Rin Launcher

> ### ⚠️ VIBE CODING（氛围编程）警告
>
> **本项目是一次「氛围编程」实践**：代码与文档由 AI（GitHub Copilot）在维护者的
> 需求与验收下生成，**没有经过专业的安全审计**。功能都尽力验证过（单元测试、冒烟、
> 实机测试），但仍然**请自行评估风险后再使用** —— 尤其是提权（UAC）、开机自启动
> 这类会碰系统的功能。发现问题欢迎提 Issue。

基于 **RinUI（PySide6 + QML）** 的桌面启动台。常驻在桌面右下角的**小窗**负责「点一下
就用」，**完整窗口**负责「把东西管起来」。目标平台 Windows 10/11。

- 常驻小窗：无边框亚克力的桌面挂件，锚在主显示器右下角（不抢焦点、不进任务栏、沉底）
- 双行面板（最多 10 格）+ 存储与磁盘区 + 系统控制（音量 / Wi-Fi / 热点），每格自由定义：文件 / 命令行 / 网址 / 按键模拟
- 配置、日志、图标都在 exe 同级的 `data/` 目录；首次启动自动生成（并自动迁移旧数据）

---

## 功能特性

| | |
| --- | --- |
| 🪟 **常驻小窗** | 亚克力无焦点桌面挂件：固定主显示器右下角、沉在普通窗口之下；双行面板 + 存储区 + 系统控制 |
| 🧩 **槽位自由定义** | 每一格都自带完整定义：文件 / 命令行 / 网址 / 按键模拟当场填完，每格独立编辑 |
| 🎛 **系统控制** | 底部一排 Win11 风格卡片：音量滑条（图标可静音）、Wi-Fi 开关、移动热点开关 |
| ⌨️ **按键模拟** | 参考 SystemTools：全局录制键盘输入或手动编辑，支持组合键与长按 |
| 🎨 **图标选择器** | 内置 / 随包 / 我的 / 从文件获取四个来源；exe·dll·lnk 提取与 ico·svg·png 导入 |
| ⚙️ **设置** | 启动方式（普通 / 管理员自启动）、主题材质、托盘、热键、动画开关、配置管理 |
| 🔐 **管理员支持** | 条目级提权（UAC）、提权前确认开关、登录时以管理员身份自启动（任务计划） |
| 🖱 **右键菜单** | 小窗每一格右键：打开 · 提权打开 · 编辑这一格 · 再加一格 |

---

## 界面导览

**常驻小窗**：贴在主显示器右下角的亚克力挂件（点得动但不抢焦点、不盖在别的窗口上）。
自上而下：标题条（右上角：编辑启动台 / 更多）→ 双行面板（≤5 格单排，更多平分两排）→
存储与磁盘区 → 系统控制条（音量 / Wi-Fi / 热点）。
每格左键启动、右键出菜单；用 `Win+D` 或热键叫回来。

**完整窗口**：侧边三页。

| 页面 | 作用 |
| --- | --- |
| 启动台 | 编辑小窗：面板最多 10 格，加 / 删 / 挪 / 改名 / 换图标；存储区配目录与磁盘入口 |
| 设置 | 常规 / 外观 / 启动台 / 热键 / 高级；全部即时生效 |
| 关于 | 版本、仓库链接、运行环境、配置位置、许可证 |

**托盘与热键**：托盘菜单提供显示/隐藏、跳页、打开配置目录、重载配置、退出；左键单击
托盘图标切换显示。全局热键默认 `Ctrl+Space`（需含至少一个修饰键）。完整窗口的关闭
按钮只收起自己，小窗照常跑。

---

## 启动方式

设置 → 常规里的「启动方式」三选一：

| 方式 | 实现 | 说明 |
| --- | --- | --- |
| 关闭 | — | 不随系统启动 |
| 登录时启动 | 注册表 `HKCU\...\Run` | 普通权限启动，无额外提示 |
| 管理员自启动 | 任务计划（任务名 “Rin Launcher”） | 登录时以最高权限启动，**不弹 UAC**；切换时需 UAC 授权一次 |

两种自启动互斥（切换到一种时自动撤掉另一种）；设置页显示的是系统里的真实状态，
手动删过任务 / 注册表项也能看出来。

---

## 快速开始

### 下载即用

1. 从 Releases 下载 `RinLauncher.zip`，解压到任意可写目录
2. 运行 `RinLauncher.exe`

数据都在同级 `data/` 子目录（首次启动自动生成）：`config.yaml`（配置）、`launcher.log`（日志）、`icons/`（图标库）、`backups/`（自动备份）。拷走整个文件夹，数据和程序一起走；放在 Program Files 这类不可写位置时会自动回退到 `%APPDATA%\RinLauncher`。

首次启动若检测到旧版 `%APPDATA%\RinLauncher` 的配置和图标，会自动拷一份到 `data/`（一次性，原名保留）。

### 源码运行

```bash
git clone https://github.com/yixuan0826/RinLauncher.git
cd RinLauncher
pip install -r requirements.txt
python -m rin_launcher.main
```

> 源码模式的数据目录仍是 `%APPDATA%\RinLauncher`（开发习惯不变），exe 模式才用 `data/`。

### 打包

默认构建**目录形态**（onedir：不用解压、启动快，正式发布用这个）：

```bash
pip install pyinstaller
pyinstaller build.spec
# 产物：dist/RinLauncher/（入口是里面的 RinLauncher.exe，整个目录一起分发）
```

应急单文件（拷贝方便，但每次启动先解压，慢一些）：

```powershell
$env:RIN_ONEFILE="1"; pyinstaller build.spec; Remove-Item Env:RIN_ONEFILE
# 产物：dist/RinLauncher.exe（约 65MB）
```

`build.spec` 会把 `qml/`、`RinUI/`、`assets/` 一并打进去；并做了两层体积过滤
（排除用不到的 PySide6 绑定与 Qt 运行库）。

---

## 数据与配置

路径：exe 同级 `data/config.yaml`（源码运行时是 `%APPDATA%\RinLauncher\config.yaml`）。
同目录还有 `backups/`（每次写盘前自动备份，保留最近 10 份）、`launcher.log`、`icons/`。

配置文件被外部程序改动会自动重新加载（0.5 秒防抖，自己的写入会被忽略）；也可以点托盘
或设置页的「重载配置」手动触发。

### 简化示例

```yaml
version: 3

launcher:
  slots:                              # 小窗格子；数组顺序 = 行内顺序，row 决定落哪块
    - {kind: "action", row: 0, action: {type: "file", target: "notepad.exe"}, label: "记事本", icon: ""}
    - {kind: "tool", row: 0, key: "configFolder", label: "", icon: ""}
    - {kind: "usb", row: 1, label: "U 盘", icon: ""}
    - {kind: "path", row: 1, label: "D 盘", path: "D:\\", icon: ""}
  storagePath: ""                     # 存储卡片目录，空 = 用户主目录

settings:
  theme: "system"                     # system | light | dark
  accentColor: "#0078d4"
  material: "tabbed"                  # tabbed（增强云母）| mica | none（完整窗口材质）
  compactAcrylic: true                # 小窗亚克力（仅 Windows）
  showTray: true
  startMinimized: false               # 启动时只留托盘，不弹小窗
  startupMode: "off"                  # off | normal（登录时启动）| admin（管理员自启动）
  animationEnabled: true              # 关掉后所有过渡动画即时完成
  adminAutoElevate: true              # 关掉后管理员动作会被拦下并提示
  confirmAdminActions: true           # 运行管理员动作前先确认
  globalHotkey: "Ctrl+Space"
  logLevel: "INFO"                    # DEBUG | INFO | WARNING | ERROR（重启生效）
```

### 槽位（`launcher.slots`）

每个槽位结构一致，靠 `kind` 区分：`action`（自带完整定义的动作）/ `tool`（内置功能）/
`path`（文件·文件夹·磁盘）/ `usb`（自动检测的可移动磁盘）；`row` 决定落在面板
（0，最多 10 格）还是存储区（1）；`label` / `icon` 为空时用目标自己的名字与图标。

内置功能 key：`launcherPage` `settings` `configFolder` `configFile`
`reload` `elevate` `hide` `quit`。

> 老格式（`apps` / `tools` 固定两行、更早的 `row: 0/1/2` 三行模型）在读取时会自动
> 翻译成新结构；老配置里引用了已下线的「快捷操作」库的格子会被丢弃，
> `actions` / `categories` 两个顶层键会在读取配置时立即从磁盘上移除。

---

## 动作类型

| 类型 | 字段 | 说明 |
| --- | --- | --- |
| `file` | `target`、`arguments`、`working_dir`、`run_as` | `target` 可以是绝对路径、相对路径，或 PATH 里的可执行文件名（如 `notepad.exe`） |
| `cmd` | `target` + `arguments` | 两者拼成一条命令交给 shell 执行 |
| `url` | `target` | 缺少协议时自动补 `https://` |
| `keyboard` | `keyboard_steps` | 按顺序回放按键 / 等待（录制 / 手动编辑，支持组合键，鼠标已移除） |

## 按键序列

`keyboard_steps` 是一个列表，语义参考 [SystemTools](https://github.com/Programmer-MrWang/SystemTools)
的「模拟键盘」：编辑器里点「开始录制键盘输入」直接录，也可以手动逐条填。元素有两种：

```yaml
- type: "key"                     # 按键
  key: "ctrl+c"                   # 名称：单键或组合键（+ 相连）；支持单字符、ctrl/alt/shift/win、
                                  # f1-f24、方向键、enter/esc/tab 等
  vk: 67                          # 虚拟键码（录制产生；执行时优先；缺省时按名称解析）
  action: "click"                 # click（单击）| press（按住）| release（释放）
  duration: 0.1                   # 这一步执行前的等待（秒）

- type: "wait"                    # 纯等待（旧版编辑器产生，仍会执行）
  duration: 0.5                   # 秒
```

编辑器布局照 SystemTools 重做：上面是**录制按钮 + 步骤列表**，下面是「操作 / 键码 /
名称 / 延迟」编辑行和「应用修改 / 新增 / 删除」。录制时全局抓真实按键，并做了一层整理：
快速点按合并成「单击」；按住期间敲别的键拆成「按住 …… 释放」（组合键录下来即可
原样回放），同键连发不会灌进列表。

执行语义与 SystemTools 一致：每步先等 `duration` 秒再动作；`click` 发送按下 + 抬起
（组合键按 `+` 顺序逐个按下、再逆序释放），`press` / `release` 用来搭配长按；序列跑完
还按着的键会被兜底释放。有 `vk` 用 `vk` 回放（键码优先），没有才解析名称。旧版「键鼠
模拟」的 `keymouse` / `keymouse_steps` 会在读入时自动迁移，其中的鼠标步骤不再支持，
迁移时会被跳过。

## 变量替换

`target` / `arguments` / `working_dir` 支持：

| 占位符 | 含义 |
| --- | --- |
| `{appdir}` | 程序所在目录（打包后是 exe 所在目录，开发运行时是当前工作目录） |
| `{configdir}` | 配置目录 |
| `{homedir}` | 用户主目录 |
| `{tempdir}` | 临时目录 |
| `{desktop}` `{documents}` `{downloads}` | 对应的用户文件夹 |

另外 `~` 和环境变量（如 `%APPDATA%`）也会被展开。

---

## 图标系统

条目、分区和槽位的 `icon` 字段有四种写法（由 `qml/components/AppIcon.qml` 统一渲染）：
`ic_fluent_*`（内置 Fluent 字体图标）、`lawnicons:*`（随包 Lawnicons）、`file:<路径>`
（图标库里的自定义图标）、空串（占位字形）。可用图标名见
[`RinUI/assets/fonts/FluentSystemIcons-Index.js`](RinUI/assets/fonts/FluentSystemIcons-Index.js)。

编辑器里点「从图标库中选择」打开图标选择器（内置 / 随包 / 我的 / 从文件获取四个分页）：
`exe`·`dll`·`lnk` 向系统取图标（快捷方式跟随目标），`ico`·`svg`·`png`·`jpg`·`bmp`
直接导入。

需要更多 Lawnicons：`python scripts/vendor_lawnicons.py --source <上游 svg 目录>`。
脚本会补 `viewBox` 适配 Qt 渲染，并按 Apache-2.0 §4(b) 在 NOTICE 里标注修改。

---

## 目录结构

```
.
├── rin_launcher/                # Python 后端
│   ├── main.py                  # 入口：装配窗口 / 托盘 / 热键 / 单实例
│   ├── config_manager.py        # 配置读写（data/ 目录策略、旧数据迁移）
│   ├── system_controls.py       # 音量 / Wi-Fi / 移动热点（pycaw + WinRT）
│   ├── action_executor.py       # 四种动作的执行引擎（含自动提权闸门）
│   ├── key_recorder.py          # 按键录制器（全局监听 → 步骤整理）
│   ├── autostart.py             # 三态启动方式（注册表 / 任务计划）
│   ├── single_instance.py       # 单实例保护（QSharedMemory + 本地套接字）
│   ├── effects.py               # 窗口材质：小窗亚克力 / 无焦点标志
│   ├── hotkey.py                # 全局热键（pynput 监听，信号回主线程）
│   ├── tray.py                  # 系统托盘（QSystemTrayIcon + QMenu）
│   └── elevation.py             # Windows UAC 提权 / 注册表自启
├── qml/
│   ├── CompactWindow.qml        # 常驻桌面右下角的小窗（启动台）
│   ├── LauncherWindow.qml       # 完整窗口（FluentWindow + NavigationView）
│   ├── pages/                   # 启动台 / 设置 / 关于
│   ├── dialogs/                 # AppDialog 基类 + 槽位编辑器、图标选择器、确认框
│   ├── components/              # AppIcon / ActionForm / KeyboardStepsEditor / CompactPanel /
│   │                            # CompactRow / CompactTile / SystemControlBar / SlotListEditor …
│   └── qmldir
├── tests/                       # pytest：配置迁移 / 数据目录 / 启动方式 / 版本号
├── RinUI/                       # RinUI 库（内联，MIT）
├── assets/                      # 应用图标 + Lawnicons SVG（含 LICENSE / NOTICE）
├── scripts/                     # build_icon.py / vendor_lawnicons.py
├── build.spec                   # PyInstaller 配置（默认 onedir）
└── requirements.txt
```

## 开发者注记

改代码前值得知道的几件事（细节都在源码注释里）：

- **RinUI 是内联的**，其中有一处本地补丁：`ComboBox` 的 `activated` 手动补发（它用的是
  自定义 `ContextMenu`，原生信号永不触发）—— 同步上游时留意保留。
- **两个窗口各有一个 QML 引擎**；`ThemeManager` 挂在 `rootContext` 上，新建窗口后要把
  两个引擎都「钉回自己那一份」（`main.py._pin_theme_managers`）。
- **下拉一律监听 `onActivated: function (index) {...}`**（属性式写法）；函数声明式不会被
  连接成信号处理器，「选了不生效」多半就是它。
- **弹窗不用 Qt Popup**：主窗是自绘窗口，`Overlay` 拿不到；`dialogs/AppDialog.qml` 是纯
  Item 遮罩 + 居中卡片，嵌套弹窗记得写 `parent: <弹窗根 id>`。
- 设置页写盘有 350ms 防抖（`pending` + 定时器）；每次写盘前自动备份到 `backups/`。

## 已知限制

- **仅 Windows**：提权（UAC）、任务计划自启动、亚克力与无焦点窗口都是 Windows 专有实现；
  非 Windows 上相关功能安全降级或直报失败，其余照常。
- **小窗高度不可调**：固定为桌面可用高度的一半；面板最多 10 格、存储区独立一条，结构固定。
- **小窗固定沉底**：永远位于普通窗口之下（桌面之上），被最大化窗口挡住属预期行为；
  热键只负责显示 / 隐藏，不会把它抬到最前。
- **托盘依赖系统支持**：`isSystemTrayAvailable()` 为假时不建托盘；此时若小窗也未显示，
  关掉完整窗口会直接退出程序。
- **管理员自启动的细节**：任务计划条目名固定为 “Rin Launcher”；移动程序位置后需要重新
  切换一次启动方式；创建 / 删除任务需要管理员权限（切换时弹一次 UAC）。
- **RinUI 自身的控制台告警**：个别 QML 库内部提示（Slider / propertyCache）不影响功能。

---

## 第三方组件与许可证

本项目以 **MIT** 许可证发布（见 [`LICENSE`](LICENSE)）。

| 组件 | 许可证 | 位置 |
| --- | --- | --- |
| [RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) | MIT | [`RinUI/LICENSE`](RinUI/LICENSE) |
| [Lawnicons](https://github.com/LawnchairLauncher/lawnicons) | Apache-2.0 | [`assets/icons/lawnicons/LICENSE`](assets/icons/lawnicons/LICENSE) |
| [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) | MIT | 随 RinUI 提供 |

Lawnicons 的图标为适配 Qt 做过修改（补 `viewBox`），已按 Apache-2.0 §4(b) 在
[`assets/icons/lawnicons/NOTICE`](assets/icons/lawnicons/NOTICE) 中标注。Apache-2.0 §6 不授予
商标权：`honkai_star_rail.svg` 是 Lawnicons 对第三方产品标识的单色演绎，此处仅用作本程序
图标，不代表任何关联或背书；其余随包图标均为 Lawnicons 贡献的 `generic_*` 通用图案。

## 致谢

- [RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) — Fluent Design 风格的 QML UI 库
- [Lawnicons](https://github.com/LawnchairLauncher/lawnicons) — 图标
- [PySide6](https://wiki.qt.io/Qt_for_Python) — Python Qt 绑定
