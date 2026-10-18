# Roadmap

> 复盘于 2026-10-16（v1.0.0 之后）。按「先基建、后功能、再发布级」推进；
> 已完成的条目直接从清单移除，历史见 git log。

## 已完成（2026-10-16）

- [x] GitHub Actions：pytest + ruff 质量门禁（推送到 main / PR 触发）
- [x] 标签发布流水线：`v*` tag → PyInstaller onedir 构建 → zip 附加到 Release
- [x] `action_executor` 测试补齐（参数拆分 / 提权闸门 / 动作分发 / 键盘回放）
- [x] RinUI 本地补丁清单（见 `RinUI/LOCAL_PATCHES.md`）
- [x] 清理未使用的 `shutil` 导入与 `pytest-qt` 开发依赖

## 待办

### 稳定性与架构

- [ ] `config_manager.py`（约 1700 行）拆分：磁盘探测 / 旧数据迁移 / 动作 sanitize /
      watchdog 监听 / QML API 分家，降低单文件心智负担
- [ ] 配置 schema 校验：手改 `config.yaml` 出错时给可读提示（现在靠 sanitize 静默兜底）
- [ ] autostart 后台回调在 QObject 销毁后仍尝试发信号（测试输出可见
      `Signal source has been deleted`）——回调查发前加防御，避免异常噪音

### 功能

- [ ] 搜索 / 快速启动面板（呼出即搜，覆盖槽位与系统控制）——当前最大体验缺口
- [ ] 更新检查：比对 GitHub latest release，提示式（不自动下载，等代码签名后再升级为自动更新）
- [ ] 应用级 i18n 接线：17 个 QML 文件已铺 `qsTr`，缺 `.ts` 提取与 `QTranslator` 装载
- [ ] 小窗多显示器适配（当前固定主显示器右下角）
- [ ] 槽位拖拽排序 / 文件夹分组

### 发布级

- [ ] 安装器（Inno Setup 或 WiX），替代「解压即用」
- [ ] 代码签名（验证身份，缓解 SmartScreen 拦截）
- [ ] 自动更新（建议排在代码签名之后）

## 原则

- 目标平台 Windows 10/11，不投入跨平台；
- 小窗「沉底、不抢焦点、高度固定」是设计边界，不是缺陷；
- 新增依赖必须说明体积 / 许可证 / 替代方案。
