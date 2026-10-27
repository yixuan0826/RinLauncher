import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 一行的槽位列表编辑器。
//
// 交互照 ClassIsland 那套「可增删排序的分组列表」来：每一项占一行，右侧一排
// 上移 / 下移 / 编辑 / 删除，顶部一个醒目的「添加一格」。比拖拽好实现、好验收，
// 键盘和触控板也都点得动。
ColumnLayout {
    id: list

    property var slots: []
    property string emptyHint: ""
    // 数字序号从 1 开始显示。
    property string unit: qsTr("项")
    // 上限；0 表示不限。满了以后「添加」会置灰。
    property int capacity: 0

    signal addRequested()
    signal editRequested(int index)
    signal removeRequested(int index)
    signal moveRequested(int index, int delta)

    readonly property bool full: capacity > 0 && slots.length >= capacity

    Layout.fillWidth: true
    spacing: 10

    // ── 工具条：数量 / 容量进度 / 添加 ──
    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Text {
            Layout.alignment: Qt.AlignVCenter
            typography: Typography.BodyStrong
            color: list.full
                ? Theme.currentTheme.colors.systemCautionColor
                : Theme.currentTheme.colors.textColor
            text: list.capacity > 0
                ? qsTr("%1 / %2 %3").arg(list.slots.length).arg(list.capacity).arg(list.unit)
                : qsTr("%1 %2").arg(list.slots.length).arg(list.unit)
        }

        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: 84
            Layout.preferredHeight: 4
            radius: 2
            visible: list.capacity > 0
            color: Theme.currentTheme.colors.controlSecondaryColor

            Rectangle {
                height: parent.height
                radius: parent.radius
                width: parent.width
                    * Math.min(1, list.slots.length / Math.max(1, list.capacity))
                color: list.full
                    ? Theme.currentTheme.colors.systemCautionColor
                    : Theme.currentTheme.colors.primaryColor
            }
        }

        Text {
            Layout.alignment: Qt.AlignVCenter
            visible: list.full
            typography: Typography.Caption
            color: Theme.currentTheme.colors.systemCautionColor
            text: qsTr("已满")
        }

        Item { Layout.fillWidth: true }

        Button {
            text: list.slots.length === 0 ? qsTr("添加第一格") : qsTr("添加一格")
            icon.name: "ic_fluent_add_20_regular"
            highlighted: true
            enabled: !list.full
            onClicked: list.addRequested()
        }
    }

    // ── 空状态：一句话 + 一个明确入口 ──
    Frame {
        Layout.fillWidth: true
        visible: list.slots.length === 0
        implicitHeight: 124
        radius: Theme.currentTheme.appearance.windowRadius
        color: "transparent"
        border.width: 1
        border.color: Theme.currentTheme.colors.cardBorderColor

        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 32, 360)
            spacing: 6

            AppIcon {
                Layout.alignment: Qt.AlignHCenter
                iconKey: "ic_fluent_add_circle_20_regular"
                iconSize: 24
                tint: Theme.currentTheme.colors.textSecondaryColor
            }

            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: list.emptyHint
            }

            Button {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("添加一格")
                icon.name: "ic_fluent_add_20_regular"
                onClicked: list.addRequested()
            }
        }
    }

    // ── 列表 ──
    Repeater {
        model: list.slots

        delegate: Frame {
            id: slotRow

            Layout.fillWidth: true
            implicitHeight: 66
            hoverable: true
            padding: 0
            radius: Theme.currentTheme.appearance.windowRadius

            MouseArea {
                id: rowMouse
                anchors.fill: parent
                anchors.rightMargin: 150   // 让出右边那四个按钮
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: list.editRequested(index)
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 8
                spacing: 10

                Text {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 18
                    horizontalAlignment: Text.AlignRight
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: (index + 1)
                }

                // 图标底板：让一排图标在视觉上有统一的重心。
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 38
                    Layout.preferredHeight: 38
                    radius: Theme.currentTheme.appearance.windowRadius
                    color: Theme.currentTheme.colors.controlSecondaryColor

                    AppIcon {
                        anchors.centerIn: parent
                        iconKey: modelData.icon || ""
                        iconSize: 22
                        tint: Theme.currentTheme.colors.textColor
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 80
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            font.bold: true
                            color: Theme.currentTheme.colors.textColor
                            text: modelData.name || qsTr("未命名")
                        }

                        // 类型胶囊：不用读副标题也能一眼看出这是哪种格子。
                        Rectangle {
                            Layout.alignment: Qt.AlignVCenter
                            implicitWidth: kindLabelText.implicitWidth + 14
                            implicitHeight: 20
                            radius: height / 2
                            color: Theme.currentTheme.colors.subtleSecondaryColor

                            Text {
                                id: kindLabelText
                                anchors.centerIn: parent
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: modelData.kindLabel || qsTr("格子")
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.NoWrap
                        elide: Text.ElideMiddle
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: list.describe(modelData)
                    }
                }

                MiniIconButton {
                    iconName: "ic_fluent_arrow_up_20_regular"
                    tip: qsTr("前移")
                    enabled: index > 0
                    onClicked: list.moveRequested(index, -1)
                }
                MiniIconButton {
                    iconName: "ic_fluent_arrow_down_20_regular"
                    tip: qsTr("后移")
                    enabled: index < list.slots.length - 1
                    onClicked: list.moveRequested(index, 1)
                }
                MiniIconButton {
                    iconName: "ic_fluent_edit_20_regular"
                    tip: qsTr("编辑这一格")
                    onClicked: list.editRequested(index)
                }
                MiniIconButton {
                    iconName: "ic_fluent_delete_20_regular"
                    tip: qsTr("移除这一格")
                    danger: true
                    onClicked: list.removeRequested(index)
                }
            }

            ToolTip.text: qsTr("点击这一行可以直接编辑")
            ToolTip.visible: rowMouse.containsMouse
            ToolTip.delay: 700
        }
    }

    // 副标题：目标 / 状态，一眼看出这一格会打开什么。
    function describe(slot) {
        if (!slot) {
            return ""
        }
        if (slot.kind === "usb") {
            return slot.available ? slot.path : qsTr("当前没有检测到")
        }
        if (slot.kind === "path") {
            return slot.exists ? slot.path : qsTr("%1（路径不存在）").arg(slot.path)
        }
        if (slot.kind === "action") {
            return slot.target || qsTr("未设置目标")
        }
        if (slot.kind === "tool") {
            return qsTr("小窗内置功能")
        }
        return ""
    }
}
