import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 恢复模式里的一组动作：一个区块标题 + 一张卡片，卡片里每行一个动作。
//
// 为什么不复用 SettingsGroup + FormRow：恢复动作是「点一下就执行」的按钮行，
// 左侧是图标 + 两行说明，右侧是动作按钮，和设置项的左标签右控件布局不一样。
ColumnLayout {
    id: group

    property string title: ""
    property string iconKey: ""
    property var actions: []

    signal triggered(string key)

    Layout.fillWidth: true
    spacing: 12

    ZoneHeader {
        Layout.fillWidth: true
        iconKey: group.iconKey
        title: group.title
    }

    Frame {
        Layout.fillWidth: true
        padding: 6
        radius: Theme.currentTheme.appearance.windowRadius

        ColumnLayout {
            anchors.fill: parent
            spacing: 2

            Repeater {
                model: group.actions

                delegate: Item {
                    id: row

                    required property var modelData

                    Layout.fillWidth: true
                    implicitHeight: 58

                    readonly property bool danger: row.modelData.danger === true

                    Rectangle {
                        anchors.fill: parent
                        radius: 6
                        color: hover.hovered
                            ? Theme.currentTheme.colors.controlSecondaryColor
                            : "transparent"
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: group.triggered(row.modelData.key)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 12

                        // 点击穿透到下面的 MouseArea；文本与图标本身不抢事件。
                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: row.modelData.icon
                            iconSize: 20
                            tint: row.danger
                                ? Theme.currentTheme.colors.systemCriticalColor
                                : Theme.currentTheme.colors.textColor
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 1

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                color: Theme.currentTheme.colors.textColor
                                text: row.modelData.title
                            }

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: row.modelData.description
                            }
                        }

                        Button {
                            Layout.alignment: Qt.AlignVCenter
                            text: qsTr("执行")
                            onClicked: group.triggered(row.modelData.key)
                        }
                    }

                    HoverHandler {
                        id: hover
                    }
                }
            }
        }
    }
}
