# AGENTS.md — Rin Launcher 接手指南

> 面向下一位接手的 AI / 工程师。最后更新：2026-11-24，基线 `v1.2.7-pre`。
> 先读完本文件再动代码。规则优先级：用户当场指令 > 本文件 > 个人偏好。
> 不确定就查代码 / 官方文档，不要凭记忆断言。

## 1. 项目是什么

Rin Launcher 是 Windows 10/11 的启动台：常驻右下角的小窗、托盘、全局热键、
启动台编辑、设置、自动更新和独立恢复模式。技术栈：

- Python 3.14（`requires-python = ">=3.14"`）
- PySide6 >= 6.6,< 6.13（当前验证 6.12.0）
- QML + RinUI 0.5.0（`rinui==0.5.0`，补丁记录见 `docs/rinui-local-patches.md`）
- Nuitka standalone 打包，UPX 只压主 exe
- GitHub Actions：`main` 跑 CI，`v*` tag 跑 Release

## 2. 不可违反的硬约束

1. **发布资产只能是 `RinLauncher.zip`**。更新器按这个文件名找资产；改名会
   直接让自动更新失效。zip 根目录必须能解出 `RinLauncher.exe`、`qml/`、
   `assets/`、`RinUI/`、Qt 运行库、`install-manifest.json`、`repair.ps1`。
2. **1.3.0 之前保持预发布**：tag 用 `vX.Y.Z-pre`，Release 必须
   `prerelease=true`、`make_latest=false`，不做安装器、不签名。SmartScreen
   提示是预期行为，不要用自签名证书“修”它。
3. **版本号单一来源**：只改 `rin_launcher/__init__.py` 的 `__version__`。
   构建时 Windows 文件版本由 `scripts/build_nuitka.py` 把 `1.2.7-pre` 转成
   `1.2.7.0`；Release 版本从 git tag 取。不要在别处再写死版本号。
4. **Nuitka + UPX 策略**：只对主 exe 执行 `upx --best`。不要压 Qt DLL /
   插件：实测冷启动会从约 1.05 s 退化到约 2.2 s，已明确拒绝。
5. **zip 体积门禁 55 MiB**（CI 用 PowerShell 的 1 MB = 1,048,576 B）。
   当前约 54.47 MiB，空间很紧；新增依赖前先估算。
6. **不要随手改更新载荷结构 / `appmodset.conf` 语义 / 单实例协议**。
   这些牵一发动全身；要改必须同时更新 `updater.py`、`app_mode.py`、
   `install-manifest.json` 生成逻辑、测试与文档。
7. **不提交运行时文件**：`data/`、`appmodset.conf`、`updates/`、`backup-*`、
   `dist/`、`build/`、`.venv*`、日志、密钥、用户配置。提交前看 `git status`。

## 3. 目录与职责

```text
rin_launcher/
  __init__.py          __version__ / APP_CODENAME 的唯一来源
  main.py              入口；启动模式、单实例、窗口创建、退出
  config_manager.py    配置读写、设置 QML 接口、重启入口、备份/存储
  app_mode.py          appmodset.conf 解析 / 写入 / 优先级
  updater.py           检查、下载、安装、回滚、更新脚本
  elevation.py         UAC、开机自启、重启辅助脚本
  powershell.py        隐藏 PowerShell + UTF-8 BOM 脚本落盘
  runtime.py           源码 / PyInstaller / Nuitka 路径语义
  single_instance.py   QSharedMemory + QLocalServer（show / quit）
  logging_setup.py     日志目录与轮转
  hotkey.py, tray.py, effects.py, drive*.py, system_*.py, ...
qml/
  CompactWindow.qml    小窗（不要随便加 QtQuick.Window）
  LauncherEditorWindow.qml / SettingsWindow.qml / RecoveryWindow.qml / OobeWindow.qml
  pages/               启动台编辑、设置及各分类页
  components/          SettingsGroup / FormRow / ZoneHeader / Compact* 等
  dialogs/             槽位编辑、图标选择、确认框等
scripts/
  build_nuitka.py      本地 / CI 构建
  build_zip.py         生成 RinLauncher.zip
  build_manifest.py    install-manifest.json 生成与校验
  lint_qml.py          qmllint 包装（CI 同一条路径）
  verify_ui.py         真机抓图，输出 build/verify-ui/
  verify_modes.py      OOBE / 恢复等模式抓图，输出 build/verify-modes/
  bench_frozen.py      冻结包冷启动基准
  repair.ps1           随包分发的安装修复脚本
tests/                 pytest；改行为必须补回归测试
docs/                  Nuitka 迁移、RinUI 补丁等长文档
.github/workflows/     ci.yml（main）、release.yml（v* tag）
```

## 4. 运行期语义（改之前必须理解）

### 4.1 路径

- 源码：`python -m rin_launcher.main`（README 的标准入口）。
  配置目录是 `%APPDATA%\RinLauncher`。
- 冻结包：`dist/RinLauncher/RinLauncher.exe`，配置在 exe 同级 `data/`。
- `runtime.bundle_root()` 是只读资源根；`runtime.app_dir()` 是安装目录。
  Nuitka 靠 `__compiled__` 识别，**不要直接判断 `sys.frozen`**。

### 4.2 `appmodset.conf`

逐行 `key==value`，布尔只认 `true` / `false`。默认键：

```text
first-run / normal-boot / failsafe / debug / channel / recovery
```

优先级：`failsafe > recovery > first-run > debug`。`recovery` 或 `failsafe`
为真时只加载恢复窗口；`normal-boot==false` 表示启动不自动显示小窗；
`channel` 是 `stable` / `prerelease` 的单一来源。

安装目录不可写时，`ConfigManager._write_app_mode()` 会退到数据目录的
`appmodset.conf` 覆盖文件。已知边界：`main.py` 在抢单实例锁之前只读安装
目录文件；数据目录覆盖由 `ConfigManager` 再合并。若将来正式支持 Program
Files 安装，需要把这段合并前移。

### 4.3 重启

- `restartWithMode("recovery")` 必须先写 `recovery==true`、
  `failsafe==false`，再重启；只有恢复窗口里的「继续使用」调用
  `restartWithMode("normal")` 才清掉两个标记。
- `safe` / `diagnostic` 是一次性命令行模式，不落盘；重启时
  `_restart_target()` 会从旧 argv 里剥掉 `--recovery` / `--safe-mode` /
  `--diagnostic`，再附加本次目标。
- 源码模式重启用 `sys.executable -m rin_launcher.main`，工作目录
  `runtime.bundle_root()`。**不要回到 `sys.argv[0]`**：`python -m` 下它
  指向包内 `main.py`，直接按路径启动会走错 bootstrap。
- **不要把 `sys.executable` 当安装 exe**：Nuitka standalone 默认把它设成
  `<安装目录>\python.exe`（构建时 Python 的 basename），这个文件并不存在；
  从旧快捷方式、8.3 短路径或改名副本启动时还可能指向别处。自启动、重启、
  提权辅助、更新 / 修复、通知注册统一走 `runtime.launch_target()`。
  `main.py` 在导入 Qt 之前会调用
  `runtime.adopt_canonical_executable()` 把它归一到
  `runtime.app_dir() / "RinLauncher.exe"`，启动日志里的 `Runtime:` 行会
  记录 `exe / raw / processImage / launchTarget`。
- 排查启动路径用 `RinLauncher.exe --runtime-info=<json>`；CI 的冻结包冒烟
  会同时验收正常启动和「复制成 python.exe 启动」两种路径。
- 重启辅助脚本会等旧 PID 消失（最多 60 s），再 `Start-Process`；拉起后观察
  1.5 s，子进程提前退出会重试（最多 5 次），全程写
  `%TEMP%\rinlauncher-restart-<pid>.log`。不要改回「固定睡 2 秒」：退出时停
  托盘 / 热键 / 监听偶尔更慢，新进程会撞上单实例锁后静默退出，表现为
  「程序关掉后再也没起来」。
- 更新安装脚本自己会等 60 s + 1.2 s，再覆盖、校验、拉起；不要把这段等待
  删掉或缩短到不可靠的固定值。

### 4.4 单实例与退出

- `QSharedMemory` 占位 + `QLocalServer`，命令只有 `show` / `quit`。
- 恢复类模式不抢锁、也不被旧实例拦截。
- 安装 / 升级 / 卸载前用 `RinLauncher.exe --quit` 让主实例优雅退出；
  它只建 `QCoreApplication`，不加载 QML、不抢锁。

### 4.5 启动顺序

`main.py`：恢复模式（命令行或 appmodset）→ 否则抢单实例锁 → 创建小窗 →
`Launcher.run()`。`run()` 里：恢复窗口 > 首次运行 OOBE > 正常小窗
（受 `startMinimized` / `normal-boot` 影响）。

## 5. UI 规则

### 5.1 设置页导航

当前实现是仿 WinUI 3 NavigationView（RinUI 的完整 `NavigationView` 自带
标题栏和 StackView，不适合塞进现有 `FluentWindowBase`）：

- 展开 280 px，折叠 48 px；`objectName: "settingsNavPane"`。
- 左上角汉堡按钮 `ic_fluent_navigation_20_regular`，40×40，
  `objectName: "settingsNavToggle"`。
- 导航项 40 px 高、20 px 图标、文字 x=48、选中圆角胶囊 + 左侧 3×16 强调条，
  折叠时悬停出 ToolTip。
- 内容标题和分类页卡片共用：
  `contentWidth = min(windowWidth - navWidth - 48, 860)`
  `contentX = max(24, (windowWidth - navWidth - contentWidth) / 2)`
  改宽度公式时两边一起改，否则标题会比卡片偏 8 px。
- `SettingsWindow` 最小 900×620，默认 1040×760。280 px 导航展开时仍要保证
  双按钮行、宽表格、更新页顶部版本栏不裁切。
- 所有设置分类页的 `Flickable` 统一：
  `contentWidth: width`、`contentHeight: content.implicitHeight + 48`、
  内容 `x/width` 用上面的公式、底部留 48 px。

### 5.2 组件与控件

- 设置分组用 `qml/components/SettingsGroup.qml`，行用 `FormRow.qml`，
  标题用 `ZoneHeader.qml`。
- **不要用 RinUI 的 `SettingItem` / `SettingCard` 替代 `FormRow`**：它把
  左侧内容限制在行宽 60%，宽输入框会被挤变形。
- 图标名必须是 `Utils.fontIconIndex` 里存在的 `ic_fluent_*`；不确定就用
  项目里已经出现的名字。`AppIcon` 支持 `lawnicons:`、`file:`、`url:`。
- `CompactWindow.qml` 在 `import RinUI` **之后**再 `import QtQuick.Window`：
  QML 里后导入的类型优先，这样 `Window` / `Text` 解析到 Qt Quick 原生类型，
  而不是 RinUI 自带标题栏与背景的窗口包装。不要调换导入顺序。
- QML 用 `qsTr()`；中文正文用全角标点；文件 UTF-8；不要在代码 / 注释 /
  提交信息里写角色口癖或梗。

### 5.3 布局检查

UI 改动至少检查：

- 1040×760 默认尺寸；
- 900×620 最小尺寸；
- 导航展开 / 折叠；
- 125% 和 150% DPI（如有条件）；
- 最后一张卡片能滚到、不被底边裁切；
- 更新页在「可安装」按钮出现时仍不溢出。

自动抓图：

```powershell
.venv-nuitka\Scripts\python.exe scripts\verify_ui.py
.venv-nuitka\Scripts\python.exe scripts\verify_modes.py
```

输出在 `build/verify-ui/`、`build/verify-modes/`，不进提交。

## 6. 本机环境与常用命令

这台机器没有 `gh`，系统 Python 也可能没装 ruff / pytest。项目虚拟环境：

```powershell
.venv-nuitka\Scripts\python.exe
```

常用检查：

```powershell
# 源码运行
.venv-nuitka\Scripts\python.exe -m rin_launcher.main

# 静态检查
.venv-nuitka\Scripts\python.exe -m ruff check rin_launcher tests scripts --no-cache
.venv-nuitka\Scripts\python.exe -m pytest tests -q
.venv-nuitka\Scripts\python.exe scripts\lint_qml.py
```

UI / 模式抓图见 5.3。构建：

```powershell
# 本地没有 MSVC 时（只用 Zig，跳过 LTO）
.venv-nuitka\Scripts\python.exe scripts\build_nuitka.py --zig --upx

# CI / 有 MSVC 时（自动 --lto=yes）
.venv-nuitka\Scripts\python.exe scripts\build_nuitka.py --upx
```

本地构建不是发布的前置条件；CI 会用 MSVC + LTO 重新构建。用户要求“直接
CI”时，不要花时间在本地压冻结包，但仍应跑源码级测试 / lint。

## 7. 修改流程（Definition of Done）

1. **先读**：`git status`、相关入口、调用方、测试。不要凭文件名猜行为。
2. **先复现**：能写失败测试就写；不能就保留日志 / 命令输出作为证据。
3. **最小改动**：只改与问题相关的代码；不顺手重构、不改行尾、不动
   lockfile、不加不必要依赖。
4. **补测试**：新增行为至少一个回归测试；重启 / 恢复 / 更新 / 单实例
   这类路径优先做纯函数或脚本内容测试，避免真弹 UAC。
5. **跑检查**：ruff + pytest + qmllint；UI 改动加 verify_ui / verify_modes。
6. **同步文档**：CHANGELOG、README（当前版本 / 版本记录）、ROADMAP；
   行为或构建变化补 `docs/`。
7. **提交**：一次一件事；`git add` 具体文件，不用 `git add -A`；
   Conventional Commits，中文正文；提交前 `git status` 和
   `git diff --check`。
8. **推送前确认**：工作区干净、版本号正确、CHANGELOG 标题能被 CI 正则
   匹配、没有 `appmodset.conf` / `data/` 混入。

## 8. 版本与文档同步清单

发布前逐项确认：

- [ ] `rin_launcher/__init__.py` 的 `__version__` 是目标版本。
- [ ] `CHANGELOG.md` 新标题严格为
      `## X.Y.Z-pre（说明）— YYYY-MM-DD`（Release 用正则按版本截取）。
- [ ] `README.md` 当前版本、构建说明里的版本、版本记录。
- [ ] `ROADMAP.md` 当前开发线与本次已完成项。
- [ ] 行为 / 构建变化涉及的 `docs/*.md`。
- [ ] 测试示例里若把旧版本当“当前版本”，改成新版本或明确标注历史。
- [ ] 没有在代码 / 文档里留下 `1.2.4-pre` 之类的过期“当前版本”。

## 9. 发布流程

### 9.1 预检

```powershell
git status --short                 # 必须干净
.venv-nuitka\Scripts\python.exe -m ruff check rin_launcher tests scripts --no-cache
.venv-nuitka\Scripts\python.exe -m pytest tests -q
.venv-nuitka\Scripts\python.exe scripts\lint_qml.py
```

### 9.2 提交与打 tag

```powershell
git add <具体文件>
git commit -m "fix(1.2.7-pre): ..."
git push origin main

git tag v1.2.7-pre
git push origin v1.2.7-pre
```

tag 必须匹配 `^v\d+\.\d+\.\d+(-[0-9A-Za-z][0-9A-Za-z.-]*)?$`，否则
Validate tag 会直接失败。`-pre` 结尾会自动 `prerelease=true`、
`make_latest=false`。

### 9.3 监控 Release

本机没有 `gh`，用 GitHub API：

```powershell
$h = @{ 'User-Agent' = 'RinLauncher-CI' }
$run = (Invoke-RestMethod -Headers $h `
  "https://api.github.com/repos/yixuan0826/RinLauncher/actions/workflows/release.yml/runs?per_page=1").workflow_runs[0]
$run.id; $run.status; $run.conclusion

Invoke-RestMethod -Headers $h `
  "https://api.github.com/repos/yixuan0826/RinLauncher/actions/runs/$($run.id)/jobs" |
  ForEach-Object { $_.jobs.steps | Select-Object conclusion, name }
```

Release 必须全部通过的关键步骤：

`Validate tag` → `Ruff` → `Pytest` → `QML lint` → `Build` →
`Smoke test frozen package` → `Clean runtime files` → `Build install manifest` →
`Upgrade dry-run` → `Package (zip)` → `Verify zip size gate` →
`Extract release notes` → `Publish release`。

### 9.4 发布后验收

```powershell
$rel = Invoke-RestMethod -Headers $h `
  "https://api.github.com/repos/yixuan0826/RinLauncher/releases/tags/v1.2.7-pre"
$rel.prerelease          # True
$rel.assets | Select-Object name, size, digest
```

必须确认：

- `prerelease=true`、`draft=false`，且不是 Latest；
- 资产唯一且名为 `RinLauncher.zip`；
- `size` 未超过 55 MiB 门禁；
- `digest` 以 `sha256:` 开头，记录到交付说明；
- Release body 是 CHANGELOG 对应版本段落，中文正常。

### 9.5 失败处理

- CI 失败：先看具体步骤日志，在主分支修复后重新提交。
- tag 已推但 Release 未发布：修复后删除本地 / 远程 tag 再重打，需先向
  用户确认。
- Release 已发布：不要移动 / 覆盖已发布 tag；发新的 `-pre` 版本，并在
  CHANGELOG 说明。删除 Release / tag、force push 必须先取得明确确认。

## 10. 已知坑（按踩坑频率排序）

1. **冻结包里 `encoding="utf-8-sig"` 会 `LookupError`**。PowerShell 脚本
   统一走 `powershell.write_script()`：`BOM_UTF8 + text.encode("utf-8")`。
2. **Nuitka 不设 `sys.frozen`**，只注入 `__compiled__`；路径判断统一走
   `runtime.py`。
3. **Nuitka 的 `sys.executable` 不是安装 exe**：standalone 默认把它设成
   `<安装目录>\python.exe`（构建 Python 的 basename），正常双击也会得到一个
   不存在的路径。自启动、重启、更新、通知注册统一用
   `runtime.launch_target()`；启动时 `adopt_canonical_executable()` 会把它
   归一到 `RinLauncher.exe`。
4. **源码重启不能用 `sys.argv[0]`**，用 `-m rin_launcher.main`。
5. **固定 sleep 重启会撞单实例锁**；必须等旧 PID 退出。
6. **恢复标记不落盘**会导致重启后回正常模式；恢复模式只认文件标记 +
   一次性命令行参数。
7. **QML 图标名不存在时是空白**，不是报错；只用已验证的 `ic_fluent_*`。
8. **设置标题与卡片宽度公式不一致**会产生 8 px 错位；改一边必须改另一边。
9. **更新器只认 `RinLauncher.zip`**；Release 不要加第二个 zip 或改资产名。
10. **zip 体积门禁很紧**（当前 54.51 / 55 MiB），新增依赖前先看产物。
11. **qmllint 的 warning 走 stderr**；CI 必须通过
    `scripts/lint_qml.py`，不要用 PowerShell 直接循环调用。
12. **本地根目录会生成 `appmodset.conf`**（源码探针 / 首次运行）；
    它被 `.gitignore` 忽略，但发布前要清掉。
13. **`gh` 不可用**；不要假设能 `gh run watch`，用 REST API 或网页。
14. **不需要本地完整构建**；CI 是发布构建的权威，除非用户明确要求本地
    冻结包验证。

## 11. 当前基线与最近工作

### 11.1 最近完成

- **1.2.3**：U 盘入口恢复为固定内置卡片，不占配置槽位。
- **1.2.4-pre**：发布构建从 PyInstaller 迁移到 Nuitka standalone；
  新增 `runtime.py` 路径兼容层、`--quit` 单实例命令、UPX 主 exe 压缩；
  `pypinyin` 懒加载；裁掉未用 Qt 模块；更新页拆出回滚区。
- **1.2.5-pre**：
  - 重启辅助脚本等待旧 PID 退出，修复软件内 / 更新后 / 恢复模式重启
    不自动拉起；
  - 源码模式重启改用 `-m rin_launcher.main`；
  - 恢复模式重启先持久化 `recovery==true`，只有「继续使用」写回正常；
  - 设置左侧导航改为 WinUI 3 NavigationView（280 / 48），标题与卡片
    统一宽度，最小窗口 900×620；
  - 新增重启与恢复标记回归测试。
- **1.2.6-pre**：
  - 重启辅助脚本等旧 PID 上限 60 s、拉起后观察 1.5 s 并在提前退出时重试，
    全程写 `%TEMP%\rinlauncher-restart-<pid>.log`；软件内重启先返回 QML 栈，
    再由 `QTimer.singleShot(0, quit)` 退出；
  - 自启动解析 `schtasks /XML` 与 `HKCU\...\Run`，校验命令是否指向当前程序；
    源码模式改用 `startup-launcher.py`；
  - 抢单实例锁前合并数据目录 `appmodset.conf` 覆盖；
  - 小窗右键菜单：快捷方式运行 / 管理员运行 / 编辑，存储卡打开 / 编辑，
    U 盘打开 / 刷新；坐标统一 `mapToGlobal`，菜单改不透明窗口 +
    DWM / Win10 region 圆角；
  - UWP 图标按真实像素面积取最大变体，图标与缩略图至少 128×128；
  - 启动时清理更新残留；托盘菜单样式、迷你条内边距；
  - 缩略图清理 / 自动备份延后到首帧之后。
- **1.2.7-pre**：
  - `runtime.launch_target()` / `adopt_canonical_executable()`：Nuitka 的
    `sys.executable` 归一到安装目录的 `RinLauncher.exe`；
  - 自启动、重启、提权辅助、更新 / 修复、通知注册改用归一后的路径；
  - 启动日志增加 `Runtime:` 快照；隐藏入口 `--runtime-info=<json>`；
  - 关于页诊断增加 Exe / Install / Startup；启动项失效时弹一次提示；
  - `assets/` 改从 `runtime.bundle_root()` 取；
  - CI 冻结包冒烟覆盖正常启动与「复制成 python.exe 启动」。

### 11.2 当前发布基线

- 分支：`main`，commit `a052473`（`fix(1.2.6-pre): 修复重启与自启动，恢复小窗右键菜单`）
- tag / Release：`v1.2.6-pre`
- Release：https://github.com/yixuan0826/RinLauncher/releases/tag/v1.2.6-pre
- Release run：`45376728651`，21 步全部成功
- main CI：`45376714549`，成功
- 资产：`RinLauncher.zip`，57,157,094 B（54.51 MiB）
- SHA-256：`4da7bc366f2d3a7caaf1a1729fe5539b138d5347324db10413ea3a760e9f6b7c`
- 测试：215 passed；qmllint 45 个文件 0 失败
- 冷启动：主 exe UPX 后约 1.05 s（历史基线，未在 1.2.6-pre 重测）

### 11.3 下一步建议

1. 更新到 1.2.7 后看启动日志的 `Runtime:` 行，确认 `exe` / `launchTarget`
   都是安装目录的 `RinLauncher.exe`；再在设置里重新选择一次「管理员自启动」。
2. 真机点一次「重启」「重启到恢复模式」「继续使用」，确认 GUI 端到端。
3. 1.3.0 前决定是否做 Inno Setup 安装器与代码签名；不做则继续便携 zip。
4. 若支持 Program Files 安装，数据目录 `appmodset.conf` 覆盖已前移到单实例
   判断之前（1.2.6-pre）；后续只需补测试。
5. 关注 zip 体积；新增依赖后先跑 CI 体积门禁。
6. Win10 22H2 用同版本冻结包复测一次小窗 / 菜单圆角与材质。
7. 更新器 / 恢复模式的新改动优先补纯逻辑测试，避免测试里真弹 UAC。

## 12. 交付格式

回复用户时用四段：

- **结论**：先给结果，事实必须真。
- **变更**：`path:line`，只列关键改动。
- **验证**：命令 + 真实输出摘要；未验证要写“未验证”+ 原因。
- **未决**：风险、待决策、需要用户点的操作。

不要把完整代码贴聊天代替落盘；改完就写文件。不要声称使用了未提供的工具。
