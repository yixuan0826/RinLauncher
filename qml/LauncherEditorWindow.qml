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

    signal closeRequested()

    onClosing: function (close) {
        close.accepted = false
        editorWindow.closeRequested()
    }

    LauncherSettingsPage {
        anchors.fill: parent
    }
}
