# Nuitka 打包迁移（1.2.4-pre）

本文件记录 1.3.0 预发布 `1.2.4-pre` 的 Nuitka 迁移结论、验收项与回滚方式。
安装器不在本版范围；发布物仍只有 `RinLauncher.zip`。

## 结论

1.2.4-pre 起，发布构建从 PyInstaller onedir 切换到 **Nuitka standalone**。
产物目录和 zip 结构保持不变，因此：

- 应用内更新仍下载并覆盖 `RinLauncher.zip`；
- `install-manifest.json`、`repair.ps1`、`data/` 同级写入、单实例行为都不变；
- 不需要修改更新器的资产名 `rinlauncher.zip`。

## 构建

本地没有 MSVC 时：

```powershell
.\.venv-nuitka\Scripts\python.exe scripts\build_nuitka.py --zig
```

CI / 正式构建（有 MSVC）：

```powershell
python scripts/build_nuitka.py
```

产物：`dist/RinLauncher/RinLauncher.exe`。随后：

```powershell
python scripts/build_manifest.py dist/RinLauncher --version 1.2.4-pre
python scripts/build_zip.py dist/RinLauncher RinLauncher.zip
```

### 关键参数

- `--mode=standalone --enable-plugin=pyside6 --include-qt-plugins=qml`
- 数据：`qml/`、`assets/`、`repair.ps1`、RinUI 包数据、WinRT `.pywinrt`、pypinyin 词库
- 隐藏模块：`comtypes.client`、`win32com.propsys.*`、`winrt.windows.*`、`watchdog.*`
- 构建后裁剪：WebEngine / 3D / Charts / Multimedia / Pdf / VirtualKeyboard /
  OpenGL 软件兜底 / 未使用 QML 模块与 `.qmltypes`。**不要**删 QtOpenGL 和
  Windows / Fusion / NativeStyle：QtQuick 默认样式解析会用到。
- 本地 Zig 构建不启用 LTO（Zig 0.17.1 链接会缺 `fdiml` / `nanl`）；CI 的 MSVC
  构建启用 `--lto=yes`。
- 主 exe 用 UPX `--best`（NRV）压缩；**不要**压 Qt DLL / pyd：完整 UPX 的 A/B
  是 1133 → 2200 ms，已拒绝。

## 2026-11-23 基线（本机 Win11，Zig）

| 指标 | 结果 |
|---|---|
| Nuitka 构建耗时 | 约 355 s（含 C 编译与 UPX，未含 pip） |
| payload | 129.7 MB，1563 个文件 |
| `RinLauncher.zip`（level-9 deflate） | **51.84 MB**（PyInstaller 1.2.3 为 71.39 MB） |
| 冻结包冷启动 | 中位数 **1054.2 ms**（3 次，启动 → 首个可见窗口，UPX exe） |
| 源码冷启动 | 约 1060 ms（`bench_startup.py`，无头） |
| 测试 | 199 passed |
| QML lint | 45 files, 0 failed |

UPX A/B（本机，3 次中位数）：

| 方案 | zip | 冷启动 |
|---|---|---|
| 不压 | 53.87 MB | 1133.4 ms |
| 只压主 exe（`--best`） | 51.8 MB | 1054.2 ms（配合 pypinyin 懒加载） |
| 压所有 exe/dll/pyd | 46.94 MB | 2199.9 ms（拒绝） |

启动优化：`pypinyin` 从模块导入改为首次搜索时加载，`app-imports` 从约
295 ms 降到约 158 ms；QML 加载仍是主要成本（约 511 ms）。旧的 2 秒系统轮询
已经在 1.2.3 实现为「小窗隐藏即停」，本次保留；另外给缩略图缓存加了 500 个
上限。

## 已验收

- 恢复模式、正常首次运行（OOBE）、小窗可见、托盘、全局热键日志正常。
- `RinLauncher.exe --quit` 在 3 秒内关闭运行中的实例。
- 删除 `RINLAUNCHER_CONFIG_DIR` 后，首次启动在 exe 同级生成 `data/config.yaml`。
- 冻结包从 `dist/RinLauncher` 直接启动，资源从产物目录加载，不回落到源码树。
- `scripts/verify_ui.py`、`scripts/verify_modes.py` 通过并产出截图。
- `install-manifest.json` 生成与校验由 CI 继续执行；升级覆盖 dry-run 保留。

## 已知限制

- 本版未做代码签名，SmartScreen 提示属预期。
- 只有便携包，没有 Inno Setup 安装器。
- Win10 22H2 的上一版实机结论可参考 1.2.3；本版冻结包的 Win10 实机复测仍建议
  在正式 1.3.0 前补一次。
- 裁剪清单与 Qt / RinUI 版本绑定；升级 Qt 后必须重跑启动冒烟和 zip 体积检查。
- `opengl32sw.dll`（软件 OpenGL 兜底）未打包；标准 D3D11 路径可用，极老显卡 /
  远程桌面异常时优先怀疑这里。

## 回滚

1. 回退 `feat/nuitka-1.2.4-pre` 的提交，恢复 `build.spec` 与 PyInstaller 版本；
2. 保留 `RinLauncher.zip` 资产名不变，旧版更新器即可继续工作；
3. 若只是发布包异常，删除对应 tag / Release 后重发，不修改已发布资产内容。
