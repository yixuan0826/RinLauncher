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

    Component.onCompleted: applyAccentColor()

    // FluentWindowBase 的默认属性是 content（只收 Item），Connections 不能直接
    // 当子对象写；挂到属性上，信号一样能收到。
    property Connections accentWatcher: Connections {
        target: ConfigManager
        function onAccentColorChanged() { applyAccentColor() }
        function onConfigChanged() { applyAccentColor() }
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
