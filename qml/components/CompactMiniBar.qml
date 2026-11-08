import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 迷你模式：单行工具条（前三个面板格 + 存储 + U 盘 + 更多）。
//
// 整条是胶囊：外层窗口高度 56，内部卡片 44 高、圆角取半高。没有设备时
// U 盘卡置灰但不隐藏，位置保持稳定。
Item {
    id: root

    property var panelSlots: []
    property var storage: ({})
    property var usbDevices: []

    signal slotActivated(var slot)
    signal storageActivated()
    // 传的是锚点 item：菜单要靠它算屏幕坐标。
    signal moreRequested(var anchor)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 6

        // 前三个固定应用：只显示图标，不显示文字。
        Repeater {
            model: root.panelSlots.slice(0, 3)

            delegate: Frame {
                Layout.preferredWidth: 44
                Layout.preferredHeight: 44
                padding: 0
                // 迷你条整体是胶囊，内部 44 高的卡片直接取半高做圆角。
                radius: 22
                border.width: 0
                color: miniMouse.containsMouse
                    ? Theme.currentTheme.colors.subtleSecondaryColor
                    : Theme.currentTheme.colors.cardColor

                AppIcon {
                    anchors.centerIn: parent
                    iconKey: modelData.icon || "ic_fluent_apps_20_regular"
                    iconSize: 22
                    tint: Theme.currentTheme.colors.textColor
                    placeholder: "ic_fluent_apps_20_regular"
                }

                MouseArea {
                    id: miniMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.slotActivated(modelData)
                }

                ToolTip.text: modelData.name || ""
                ToolTip.visible: miniMouse.containsMouse
            }
        }

        // 固定存储位置：与 Wi-Fi 开关同样的卡片样式。
        Frame {
            Layout.preferredWidth: 96
            Layout.preferredHeight: 44
            padding: 0
            radius: 22
            border.width: 0
            color: storageMouse.containsMouse
                ? Theme.currentTheme.colors.subtleSecondaryColor
                : Theme.currentTheme.colors.cardColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 6

                AppIcon {
                    Layout.alignment: Qt.AlignVCenter
                    iconKey: "ic_fluent_storage_20_regular"
                    iconSize: 20
                    tint: Theme.currentTheme.colors.textColor
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font.pixelSize: Theme.currentTheme.typography.captionSize
                        font.weight: Font.DemiBold
                        color: Theme.currentTheme.colors.textColor
                        text: root.storage.label || qsTr("存储")
                    }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font.pixelSize: Theme.currentTheme.typography.captionSize - 1
                        color: Theme.currentTheme.colors.textSecondaryColor
                        // 卡片只有 96px：副标题只放容量数字，「剩余」交给上方的
                        // ToolTip，否则整句会被省略号吃掉后半段。
                        text: root.storage.available
                            ? String(root.storage.free)
                            : qsTr("不可用")
                    }
                }
            }

            MouseArea {
                id: storageMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.storageActivated()
            }
            ToolTip.text: String(root.storage.path || "")
            ToolTip.visible: storageMouse.containsMouse
        }

        // U 盘快捷开关：没有设备时置灰禁用，不隐藏，位置稳定。
        Frame {
            Layout.preferredWidth: 96
            Layout.preferredHeight: 44
            padding: 0
            radius: 22
            border.width: 0
            opacity: root.usbDevices.length > 0 ? 1 : 0.55
            color: usbMouse.containsMouse && root.usbDevices.length > 0
                ? Theme.currentTheme.colors.subtleSecondaryColor
                : Theme.currentTheme.colors.cardColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 6

                AppIcon {
                    Layout.alignment: Qt.AlignVCenter
                    iconKey: "ic_fluent_usb_plug_20_regular"
                    iconSize: 20
                    tint: Theme.currentTheme.colors.textColor
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font.pixelSize: Theme.currentTheme.typography.captionSize
                        font.weight: Font.DemiBold
                        color: Theme.currentTheme.colors.textColor
                        text: root.usbDevices.length > 0
                            ? (root.usbDevices[0].name || qsTr("U 盘"))
                            : qsTr("U 盘")
                    }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font.pixelSize: Theme.currentTheme.typography.captionSize - 1
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: root.usbDevices.length > 0
                            ? String(root.usbDevices[0].free || "?")
                            : qsTr("未插入")
                    }
                }
            }

            MouseArea {
                id: usbMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: root.usbDevices.length > 0
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: ConfigManager.openRemovableDrive()
            }
            ToolTip.text: root.usbDevices.length > 0
                ? qsTr("%1 · 剩余 %2")
                    .arg(root.usbDevices[0].name || "U 盘")
                    .arg(root.usbDevices[0].free || "?")
                : qsTr("没有检测到 U 盘")
            ToolTip.visible: usbMouse.containsMouse
        }

        Item { Layout.fillWidth: true }

        ToolButton {
            id: moreButton
            objectName: "compactMiniMoreButton"
            Layout.preferredWidth: 36
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter
            icon.name: "ic_fluent_more_vertical_20_regular"
            ToolTip.text: qsTr("更多")
            ToolTip.visible: hovered
            onClicked: root.moreRequested(moreButton)
        }
    }
}
