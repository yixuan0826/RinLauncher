import QtQuick 2.15
import RinUI

import "pages"

// 设置窗口：左侧分类栏（通用 / 个性化 / 更新 / 备份 / 关于与鸣谢）。
FluentWindowBase {
    id: settingsWindow

    width: 1000
    height: 760
    minimumWidth: 860
    minimumHeight: 600
    title: qsTr("设置")
    titleEnabled: true

    // 本窗口换色时自己已经当场应用；这里接住其他来源（恢复默认 / 导入配置 /
    // 外部修改 config.yaml）的强调色变化。
    function applyAccentColor() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var value = ConfigManager.accentColor
        if (value && value.length > 0) {
            Utils.primaryColor = value
        }
    }

    function applyThemeSetting() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var mode = String(ConfigManager.getSettings().theme || "system")
        Theme.setTheme(mode === "light" ? Theme.mode.Light
                      : mode === "dark" ? Theme.mode.Dark
                      : Theme.mode.Auto)
    }

    // 材质应用失败（DWM 关闭 / 远程桌面）时的实色兜底；由 Python 在
    // apply_backdrop 里设置。正常 Win11 / Win10 下始终为 false。
    property bool materialFallback: false

    Rectangle {
        objectName: "materialFallback"
        parent: settingsWindow.contentItem
        anchors.fill: parent
        z: -0.5
        radius: Theme.currentTheme.appearance.windowRadius
        color: Theme.currentTheme.colors.backgroundColor
        visible: settingsWindow.materialFallback
    }

    Component.onCompleted: {
        applyAccentColor()
        applyThemeSetting()
    }

    // FluentWindowBase 的默认属性是 content（只收 Item），Connections 不能直接
    // 当子对象写；挂到属性上，信号一样能收到。
    property Connections accentWatcher: Connections {
        target: ConfigManager
        function onAccentColorChanged() { applyAccentColor() }
        function onConfigChanged() { applyAccentColor() }
        // 重置 / 恢复 / 导入会整份替换配置：主题也要跟着重放。
        function onSettingsChanged() { applyThemeSetting() }
    }

    signal closeRequested()

    onClosing: function (close) {
        close.accepted = false
        settingsWindow.closeRequested()
    }

    SettingsPage {
        anchors.fill: parent
    }
}
