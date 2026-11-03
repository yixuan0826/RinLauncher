import QtQuick 2.15
import QtQuick.Layouts 2.15
import RinUI

// 应用内轻提示。形状、圆角、配色、字体全部走 RinUI 令牌，不另起一套视觉。
//
// 常驻小窗有自己的自绘 toast（窗口没有 FloatLayer 容器），设置 / 编辑 / 恢复
// 这些完整窗口统一用这一个组件。
Item {
    id: root

    property string message: ""
    property string severity: "info"
    property int timeout: 2800
    readonly property bool active: opacity > 0

    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    anchors.bottom: parent ? parent.bottom : undefined
    anchors.bottomMargin: 20
    width: Math.min(parent ? parent.width - 48 : 360, toastFrame.implicitWidth)
    height: toastFrame.implicitHeight
    opacity: 0
    visible: opacity > 0
    z: 2000

    function show(text, level) {
        root.message = String(text || "")
        root.severity = String(level || "info")
        root.opacity = 1
        hideTimer.restart()
    }

    function dismiss() {
        root.opacity = 0
        hideTimer.stop()
    }

    function accent() {
        if (severity === "success") return Theme.currentTheme.colors.systemSuccessColor
        if (severity === "warning") return Theme.currentTheme.colors.systemCautionColor
        if (severity === "error") return Theme.currentTheme.colors.systemCriticalColor
        return Theme.currentTheme.colors.systemAttentionColor
    }

    function iconName() {
        if (severity === "success") return "ic_fluent_checkmark_circle_20_filled"
        if (severity === "warning") return "ic_fluent_error_circle_20_filled"
        if (severity === "error") return "ic_fluent_dismiss_circle_20_filled"
        return "ic_fluent_info_20_filled"
    }

    Behavior on opacity {
        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
    }

    Frame {
        id: toastFrame
        width: root.width
        implicitHeight: body.implicitHeight + 18
        padding: 0
        radius: Theme.currentTheme.appearance.windowRadius
        color: Theme.currentTheme.colors.backgroundAcrylicColor
        border.color: Theme.currentTheme.colors.flyoutBorderColor

        RowLayout {
            id: body
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 8
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            spacing: 10

            Icon {
                Layout.alignment: Qt.AlignVCenter
                name: root.iconName()
                size: 18
                color: root.accent()
            }

            Text {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: root.message
            }

            ToolButton {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30
                icon.name: "ic_fluent_dismiss_20_regular"
                onClicked: root.dismiss()
            }
        }
    }

    Timer {
        id: hideTimer
        interval: root.timeout
        onTriggered: root.opacity = 0
    }
}
