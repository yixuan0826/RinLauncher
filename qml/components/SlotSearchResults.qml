import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 启动台搜索结果：每行一个槽位（图标 + 名称 + 位置说明），右侧「打开 / 编辑」。
//
// 只负责画，不查数据 —— 搜索走 ConfigManager.searchSlots()，支持全拼与首字母。
ColumnLayout {
    id: root

    property var slots: []
    // tool 类槽位由小窗自己处理窗口操作，编辑器里只让编辑不让打开。
    property bool allowRun: true

    signal runRequested(var slot)
    signal editRequested(var slot)

    Layout.fillWidth: true
    spacing: 2

    Repeater {
        model: root.slots

        delegate: Item {
            id: row

            required property var modelData

            Layout.fillWidth: true
            implicitHeight: 52

            Rectangle {
                anchors.fill: parent
                radius: 6
                color: hover.hovered
                    ? Theme.currentTheme.colors.controlSecondaryColor
                    : "transparent"
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 12

                AppIcon {
                    Layout.alignment: Qt.AlignVCenter
                    iconKey: row.modelData.icon || ""
                    iconSize: 24
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        color: Theme.currentTheme.colors.textColor
                        text: row.modelData.name || qsTr("未命名")
                    }

                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: [row.modelData.kindLabel || "",
                               row.modelData.path || row.modelData.target || ""]
                            .filter(function (part) { return part.length > 0 }).join(" · ")
                    }
                }

                Button {
                    Layout.alignment: Qt.AlignVCenter
                    text: qsTr("打开")
                    visible: root.allowRun && row.modelData.kind !== "tool"
                    onClicked: root.runRequested(row.modelData)
                }

                Button {
                    Layout.alignment: Qt.AlignVCenter
                    text: qsTr("编辑")
                    highlighted: true
                    onClicked: root.editRequested(row.modelData)
                }
            }

            HoverHandler {
                id: hover
            }
        }
    }
}
