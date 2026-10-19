import QtQuick 2.15
import RinUI

import "pages"

// 启动台编辑窗口：只放启动台编辑页，不再和设置共用导航壳。
FluentWindowBase {
    id: editorWindow

    width: 1040
    height: 740
    minimumWidth: 900
    minimumHeight: 580
    title: qsTr("启动台设置")
    titleEnabled: true

    // 强调色是全局设置，但 Theme/Utils 是每个 QML 引擎各自的单例：
    // 本窗口创建时应用一次，之后跟着 ConfigManager 的信号走。
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
        editorWindow.closeRequested()
    }

    LauncherSettingsPage {
        anchors.fill: parent
    }
}
