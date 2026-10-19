pragma Singleton
import QtQuick 2.15
import QtQuick.Window 2.15
import "../assets/fonts/FluentSystemIcons-Index.js" as Icons
import "../themes"
import "../utils"

QtObject {
    property string fontFamily: Qt.platform.os === "windows"
        ? "Microsoft YaHei" : Qt.application.font.family   // 默认字体
    property string iconFontFamily: FontIconLoader.name
    property string fontIconSource: Qt.resolvedUrl("../assets/fonts/FluentSystemIcons-Resizable.ttf")  // 字体图标路径
    property string fontIconIndexSource: Qt.resolvedUrl("../assets/fonts/FluentSystemIcons-Index.js")  // 字体图标索引路径
    property var fontIconIndex: Icons.FluentIcons // 字体图标索引

    property color primaryColor: "#605ed2" // 默认主题色
    // 图标 / 强调前景用的强调色：在主题已经调整过的主色上再加一道亮度保险 ——
    // 深色主题下保证足够亮、浅色主题下保证足够暗，系统主题色特别暗 / 特别亮时
    // 小图标也不会糊在背景里。只用于前景，填充与描边仍用 primaryColor。
    readonly property color accentIconColor: {
        var themed = (typeof Theme !== "undefined" && Theme.currentTheme)
                     ? Theme.currentTheme.colors.primaryColor : Qt.color(primaryColor)
        var dark = (typeof Theme !== "undefined" && Theme.currentTheme)
                   ? Theme.isDark() : false
        var value = themed.hsvValue
        var target = dark ? Math.max(value, 0.78) : Math.min(value, 0.72)
        if (Math.abs(target - value) < 0.001) {
            return themed
        }
        var hue = themed.hsvHue
        return Qt.hsva(hue < 0 ? 0 : hue, themed.hsvSaturation, target, 1.0)
    }
    property QtObject colors: Theme.currentTheme.colors // 主题颜色
    property QtObject appearance: Theme.currentTheme.appearance // 界面外观
    property QtObject typography: Theme.currentTheme.typography // 字体

    property int windowDragArea: 5 // 窗口可拖动范围 (px)
    property int dialogMaximumWidth: 600 // 对话框最大宽度 (px)
    property int dialogMinimumWidth: 320 // 对话框最小宽度 (px)

    property bool backdropEnabled: false // 是否启用背景特效
    property int animationSpeed: 250 // 动画速度 (ms)
    property int animationSpeedExpander: 333 // 动画速度 (ms)
    property int animationSpeedFaster: 167 // 动画速度 (ms)
    property int appearanceSpeed: 187 // 界面切换速度 (ms)
    property int animationSpeedMiddle: 667 // 动画速度 (ms)
    property int progressBarAnimationSpeed: 1550 // 进度条动画速度 (ms)

    // 当前屏幕 devicePixelRatio（只读诊断用）。
    // Qt Quick 的宽高 / font.pixelSize 已是逻辑像素，布局中不要再乘 dpiScale。
    readonly property real dpiScale: Screen.devicePixelRatio || 1.0

    function loadFontIconIndex() {
        Qt.include(fontIconIndexSource);
    }

    // @deprecated 请勿用于布局或字号。Qt Quick 尺寸已是逻辑像素，再乘 dpr 会双重缩放。
    // 仅保留 API 兼容；行为为恒等映射，并在首次调用时警告。
    property bool _dpWarned: false
    function dp(value) {
        if (!_dpWarned) {
            _dpWarned = true
            console.warn(
                "[RinUI] Utils.dp() is deprecated: Qt Quick uses logical pixels. "
                + "Do not multiply layout/font sizes by devicePixelRatio. Returning value as-is."
            )
        }
        return value
    }

    Component.onCompleted: {
        console.log("Font Family: " + fontFamily)
        console.log("[RinUI] DPI Scale Factor (devicePixelRatio): " + dpiScale)
        console.log(
            "[RinUI] HiDPI note: avoid layer+OpacityMask on text containers; "
            + "PassThrough scale policy is set in RinUI/__init__.py"
        )
    }
}
