import QtQuick 2.15
import RinUI

// 小窗的简易 toast：常驻桌面的挂件没有 FloatLayer 那种容器，自绘一条更合适。
//
// 用法：``toast.show(qsTr("已复制"))``。重复调用会重置计时，不做队列 ——
// 小窗上同时多条提示本来就是噪音。
Rectangle {
    id: root

    property int displayMs: 2600

    z: 900
    width: Math.min(textItem.implicitWidth + 24, parent ? parent.width - 32 : 240)
    height: 32
    radius: Theme.currentTheme.appearance.windowRadius
    color: Theme.currentTheme.colors.primaryColor
    opacity: 0
    visible: opacity > 0

    function show(message) {
        textItem.text = message
        opacity = 1
        hideTimer.restart()
    }

    Behavior on opacity {
        NumberAnimation { duration: 160 }
    }

    Text {
        id: textItem
        anchors.centerIn: parent
        width: parent.width - 20
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        color: "white"
        font.pixelSize: Theme.currentTheme.typography.captionSize
        text: ""
    }

    Timer {
        id: hideTimer
        interval: root.displayMs
        onTriggered: root.opacity = 0
    }
}
