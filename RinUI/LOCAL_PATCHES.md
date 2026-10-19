# RinUI 本地补丁清单

本目录是内联的 RinUI（MIT，上游：<https://github.com/RinLit-233-shiroko/Rin-UI>）。
同步上游时，下面三处本地补丁必须手工保留（或移植后再同步），本文件也一并保留。

## 1. ComboBox 手动补发 `activated`

`components/BasicInput/ComboBox.qml` 的 `handleItemSelected()`（约 146–154 行）。

组件用自定义 `ContextMenu`（普通 Popup）实现下拉，不走 Qt 菜单的激活通道，
原生 `activated` 信号永远不会发。`handleItemSelected()` 里手动
`root.activated(index)` 补一发，外部写的 `onActivated` 才能拿到选中的项。

- 症状（丢掉补丁）：所有监听 `onActivated` 的下拉「选了不生效」。

## 2. Menu 高度钉回 `implicitHeight`

`components/MenusAndToolbars/Menu.qml`（约 104–114 行）。

enter 动画会把 `height` 定格在动画结束那一刻的 `implicitHeight`；菜单条目
在首开后布局才稳定时，height 就会停在偏小的值上，表现为「最后一行被裁掉」。
补丁给 `root` 加了：

```qml
Binding {
    target: root
    property: "height"
    value: root.implicitHeight
    when: !enter.running
    restoreMode: Binding.RestoreNone
}
```

- 症状（丢掉补丁）：菜单最后一行显示不全。

## 3. Slider 手柄不再读 `parent`

`components/BasicInput/Slider.qml` 的 `handle` 定位（约 126–132 行）。

`handle` 挂载前 `parent` 还是 `null`，原来的 `parent.width / parent.height`
会在控件构造阶段报 `Cannot read property 'height' of null`。改为读 `root`，
位置语义不变。

- 症状（丢掉补丁）：设置页 / 音量滑条创建时控制台刷空引用错误。

## 4. `Utils.accentIconColor`

`themes/utils.qml`：新增只读属性 `accentIconColor`，按当前深浅主题给强调色
加一个亮度下限 / 上限（深色主题提亮、浅色主题压暗），供图标与强调文字着色。

- 症状（丢掉补丁）：系统主题色偏暗时，启动台里的小图标几乎糊在深色卡片上。

## 同步建议

1. 用上游 release 全目录对比 `RinUI/`，逐个文件过 diff；
2. 合并前 grep 两个文件里的 `本地` / `本地兼容补丁` 字样，确认补丁还在；
3. 同步后冒烟：随便打开一个下拉（选中后确认联动生效）+ 打开「…」更多菜单
   （看最后一行是否完整）。
