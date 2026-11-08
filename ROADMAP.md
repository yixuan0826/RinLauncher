# Roadmap

> 复盘于 2026-10-16（v1.0.0 之后）。按「先基建、后功能、再发布级」推进；
> 已完成的条目直接从清单移除，历史见 git log。
> 当前开发线：**1.2.1（1.2.x 维护线）**；1.2.0（Hoshimi Miyabi）已发布，
> 1.1.7 ~ 1.1.15 是它的预览版。

## 已完成（2026-11-08，1.2.1）

- [x] 依赖全面升级：Python 3.14.10 / PySide6 6.12.0 / watchdog 7.1 / winrt 4!10
- [x] RinUI 从内联 0.4.4.1 改成 pip 0.5.0，补丁清单归档到 `docs/rinui-local-patches.md`
- [x] 新增 `RinComboBox` 包装器：0.5.0 不再发 `activated`，改由弹层 `itemSelected` 转发（9 个文件 20 处）
- [x] `config_manager.py` 第一批拆分：默认值与清洗规则 → `config_schema.py`，监听器 → `config_watcher.py`
- [x] `updater.py` 拆分：Release 列表与 Markdown 解析 → `updater_release.py`
- [x] 无用代码清理：无引用的常量、方法与属性共 14 处（已交叉核对 QML / 测试）
- [x] 构建期依赖断言：拼音搜索与 Windows Toast 缺包时直接失败，不再静默降级
- [x] `system_controls.py` 拆分：音量后端 → `system_audio.py`，Wi-Fi / 热点 →
  `system_network.py`，外壳只留 QML 契约与线程调度（839 → 327 行）
- [x] `CompactWindow.qml` 拆分：存储行 / 迷你条 / 自绘提示 → `CompactStorageRow` /
  `CompactMiniBar` / `CompactToast`（965 → 557 行）
- [x] `SlotEditorDialog.qml` 拆分：预览卡 / 类型选择 / 目标字段 → `SlotPreviewCard` /
  `SlotKindSelector` / `SlotTargetFields`（606 → 407 行）
- [x] WinRT 工作线程懒启动：恢复模式与仅开设置页时不再白起线程和 winrt 导入链
- [x] 依赖清单去水：`darkdetect` 无直接引用（由 rinui 传递），从本项目声明里移除
- [x] 迷你条存储卡 / U 盘卡副标题改为纯容量数字，96px 卡宽下不再被省略号吃掉
- [x] CI 增加 QML lint（不再只在 tag 时跑）；导入路径改为 pip 安装位置
- [x] 归档 1.1.12-pre / 1.1.13-pre / 1.1.15-pre / 1.2.0（细节见 CHANGELOG）

## 已完成（2026-11-03，1.1.11-pre）

- [x] 迷你模式：单行工具条（前三个固定应用 + 存储 + U 盘 + 更多）
- [x] 悬浮球：右下角置底 / 无焦点 / 不可拖拽，单击展开三种模式入口
- [x] 首次启动 OOBE，可从设置重新打开
- [x] `appmodset.conf` 取代 `channel.txt`，统一启动模式与发布通道
- [x] 窗口左下 / 右下与 X / Y 偏移；三套形态独立透明度
- [x] 检测 Wallpaper Engine 时改用 Acrylic，响应动态壁纸叠层
- [x] 开始菜单后台扫描与全类别缩略图缓存
- [x] U 盘设备名 / 多分区合并容量 / 一键打开全部分区
- [x] 系统通知快速注册并发送测试通知
- [x] Python 3.14 与 WinRT 4.1+

## 已完成（2026-10-29，1.1.10-pre）

- [x] 恢复模式独立成进程：主程序退出 → 新进程只加载恢复窗口；新增小窗「更多」、
      托盘菜单与 `--recovery` 三个入口
- [x] 发布流水线加质量门禁：`ruff` + `pytest` + `pyside6-qmllint`，红灯 tag 发不出去
- [x] 打包体积：剔除未用到的 Qt Quick Controls 样式、调试图插件与非中文翻译
- [x] `config_manager.py` 拆分第一批：磁盘探测 → `drives.py`，备份 → `backups.py`，
      图标库 → `icon_store.py`（2304 → 1990 行）
- [x] 小窗多显示器定位：改用主屏真实可用区域，不再跑到最右侧副屏
- [x] Python 最低版本与 CI / 发布流水线统一到 3.12

## 已完成（2026-10-27，1.1.7-pre）

- [x] 恢复模式：安全 / 诊断模式重启、恢复备份、重置与清理
- [x] 更新：提示式检查 + 手动安装 + GitHub `digest` 校验；回滚改为「在线选旧版本」
- [x] 通知类别 × 渠道（应用内 / 托盘气泡 / Windows 原生 Toast）
- [x] 风险行为库：危险命令、系统目录、开机启动目录、提权动作的保存前二次确认
- [x] 启动台编辑页拼音搜索（全拼 / 首字母）
- [x] 磁贴尺寸三档，按面板宽度自动决定每行格数
- [x] 槽位在编辑器内上下移动（拖拽排序仍待做）

## 已完成（2026-10-16）

- [x] GitHub Actions：pytest + ruff 质量门禁（推送到 main / PR 触发）
- [x] 标签发布流水线：`v*` tag → PyInstaller onedir 构建 → zip 附加到 Release
- [x] `action_executor` 测试补齐（参数拆分 / 提权闸门 / 动作分发 / 键盘回放）
- [x] RinUI 本地补丁清单（现归档为 `docs/rinui-local-patches.md`）
- [x] 清理未使用的 `shutil` 导入与 `pytest-qt` 开发依赖

## 待办

### 稳定性与架构

- [ ] `config_manager.py` 继续拆分：配置归一化 / 动作 sanitize / watchdog 监听 /
      QML facade 分家（第一批已把磁盘、备份、图标拆走，当前约 1990 行）
- [ ] 配置 schema 校验：手改 `config.yaml` 出错时给可读提示（现在靠 sanitize 静默兜底）
- [ ] `updater.py` 拆分：版本解析 / 下载 / 安装脚本生成（当前约 1075 行）
- [ ] autostart 后台回调在 QObject 销毁后仍尝试发信号（测试输出可见
      `Signal source has been deleted`）——回调查发前加防御，避免异常噪音

### 功能

- [ ] 小窗内搜索面板：小窗带 `WindowDoesNotAcceptFocus`，键盘输入收不到；
      需要另开一个可聚焦的搜索浮层（1.2.0 目标）
- [ ] 槽位拖拽排序 / 文件夹分组（现在只能上下移动）

> 应用级 i18n **不做**：项目只面向中文用户，QML 里的 `qsTr` 保留原样，
> 不再投入 `.ts` 提取与 `QTranslator` 装载。

### 发布级

- [ ] 安装器（Inno Setup 或 WiX），替代「解压即用」
- [ ] 代码签名（验证身份，缓解 SmartScreen 拦截）
- [ ] 自动更新（建议排在代码签名之后）

## 原则

- 目标平台 Windows 10/11，不投入跨平台；
- 小窗「沉底、不抢焦点、高度固定」是设计边界，不是缺陷；
- 新增依赖必须说明体积 / 许可证 / 替代方案。
