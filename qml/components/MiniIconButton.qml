import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI

// 列表行里的迷你图标按钮。
//
// 为什么不用 RinUI 的 ToolButton：它的隐式尺寸跟着主题走，一排四五个就把窄列
// 挤爆（设置页列表的行内按钮就是这么溢出的）。这里固定 28×28，宽度可预期，行内排布
// 才稳。悬停提示沿用统一的 ToolTip。
Item {
    id: button

    property string iconName: ""
    property string tip: ""
    property bool danger: false
    property int iconSize: 16

    signal clicked()

    implicitWidth: 28
    implicitHeight: 28
    opacity: enabled ? 1 : 0.35

    Rectangle {
        anchors.fill: parent
        radius: 6
        color: pointer.containsMouse && button.enabled
            ? Theme.currentTheme.colors.controlSecondaryColor
            : "transparent"

        Behavior on color {
            ColorAnimation { duration: 100 }
        }
    }

    AppIcon {
        anchors.centerIn: parent
        iconKey: button.iconName
        iconSize: button.iconSize
        tint: button.danger
            ? Theme.currentTheme.colors.systemCriticalColor
            : Theme.currentTheme.colors.textColor
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: button.clicked()
    }

    ToolTip.visible: pointer.containsMouse && button.tip.length > 0
    ToolTip.text: button.tip
    ToolTip.delay: 600
}
