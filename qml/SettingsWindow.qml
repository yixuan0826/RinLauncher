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

    signal closeRequested()

    onClosing: function (close) {
        close.accepted = false
        settingsWindow.closeRequested()
    }

    SettingsPage {
        anchors.fill: parent
    }
}
