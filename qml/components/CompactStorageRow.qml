import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 小窗第三行：存储位置卡 + 固定的 U 盘卡 + 老配置遗留的磁盘路径卡。
//
// 卡片宽度「单卡铺开、多卡等宽、再多就横向滚动」；盒子固定 72 高（卡 66），
// 与底部的系统控制条同一节奏。数据由 CompactWindow 在 reload / refreshLive 里喂。
//
// 从 CompactWindow.qml 拆出来：这段原来占着小窗文件近两百行，把窗口配置、
// 位置计算和交互逻辑全挤到看不见。
Item {
    id: root
    objectName: "storageRow"

    // 存储位置（getStorageInfo / refreshStorageInfo 的返回值）。
    property var storage: ({})
    // 存储行槽位（row === 1）：老配置遗留的 path 入口。
    property var slots: []
    // 可移动磁盘（getRemovableDevices 的返回值）：固定卡片，不来自槽位配置。
    property var usbDevices: []

    signal storageActivated()
    signal slotActivated(var slot)
    signal storageContextRequested(real x, real y)
    signal usbContextRequested(real x, real y)

    implicitHeight: 72
    readonly property int cardHeight: 66

    // 至少两张卡（存储 + U 盘），超过两张就等宽压缩，再多横向滚动。
    // 之前统一 202，两张卡就会顶出可视区、还剩半截在滚动里。
    readonly property real cardWidth: {
        var count = 2 + root.slots.length
        return Math.max(160, Math.min(202,
            (scroller.width - (count - 1) * 8) / count))
    }

    function slotDetail(slot) {
        if (!slot) return ""
        if (slot.kind === "path" && slot.pathType === "file") {
            return slot.exists === false ? qsTr("文件不可用") : String(slot.path || "")
        }
        return slot.exists === false ? qsTr("路径不可用") : String(slot.path || "")
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        clip: true
        contentWidth: content.implicitWidth
        contentHeight: height
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentWidth > width + 1

        Row {
            id: content
            x: Math.max(0, (scroller.width - implicitWidth) / 2)
            y: Math.max(0, (scroller.height - implicitHeight) / 2)
            spacing: 8

            // 固定的存储卡片（不是槽位，第三行的头一张）。
            Frame {
                width: root.cardWidth
                height: root.cardHeight
                padding: 0
                radius: Theme.currentTheme.appearance.windowRadius
                // 云母已经定义了卡片的边界，再描一圈边就显得脏。
                border.width: 0

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: {
                        if (mouse.button === Qt.RightButton) {
                            var global = mapToGlobal(mouse.x, mouse.y)
                            root.storageContextRequested(global.x, global.y)
                        } else {
                            root.storageActivated()
                        }
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 10

                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        iconKey: "ic_fluent_storage_20_regular"
                        iconSize: 24
                        tint: Theme.currentTheme.colors.textColor
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                                font.weight: Font.DemiBold
                                color: Theme.currentTheme.colors.textColor
                                text: root.storage.label || qsTr("存储位置")
                            }

                            Text {
                                font.pixelSize: Theme.currentTheme.typography.captionSize
                                color: Theme.currentTheme.colors.textSecondaryColor
                                // 这一行很窄：带上总量会把左边的目录名挤成
                                // 「w...e」，总量留给提示气泡，进度条本身也表达了占比。
                                text: root.storage.available
                                    ? qsTr("剩余 %1").arg(root.storage.free)
                                    : qsTr("容量未知")
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 6
                            radius: 3
                            color: Theme.currentTheme.colors.controlSecondaryColor

                            Rectangle {
                                height: parent.height
                                radius: parent.radius
                                width: parent.width * Math.min(100,
                                    Math.max(0, root.storage.percent || 0)) / 100
                                color: Theme.currentTheme.colors.primaryColor

                                // 占用率每 2.5 秒重读一次，直接赋宽度会一跳一跳。
                                Behavior on width {
                                    NumberAnimation {
                                        duration: 260
                                        easing.type: Easing.OutCubic
                                    }
                                }
                            }
                        }
                    }
                }

                ToolTip.text: root.storage.available
                    ? qsTr("%1\n剩余 %2 / 共 %3")
                        .arg(root.storage.path)
                        .arg(root.storage.free)
                        .arg(root.storage.total)
                    : String(root.storage.path || "")
            }

            // U 盘卡片：内置功能，固定跟在存储卡后面。不占槽位、不可增删改，
            // 没插盘时留一张灰卡，位置和顺序都不变。
            Frame {
                id: usbCard
                objectName: "storageUsbCard"

                readonly property var device: root.usbDevices.length > 0
                    ? root.usbDevices[0] : null
                readonly property int percent: device
                    ? Math.round(Number(device.percent || 0)) : 0

                width: root.cardWidth
                height: root.cardHeight
                padding: 0
                radius: Theme.currentTheme.appearance.windowRadius
                border.width: 0
                opacity: device ? 1 : 0.55

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: usbCard.device !== null
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: {
                        if (mouse.button === Qt.RightButton) {
                            if (!usbCard.device) {
                                return
                            }
                            var global = mapToGlobal(mouse.x, mouse.y)
                            root.usbContextRequested(global.x, global.y)
                        } else {
                            ConfigManager.openRemovableDrive()
                        }
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 10

                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        iconKey: "ic_fluent_usb_plug_20_regular"
                        iconSize: 24
                        tint: usbCard.device
                            ? Theme.currentTheme.colors.textColor
                            : Theme.currentTheme.colors.textSecondaryColor
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                            font.weight: Font.DemiBold
                            color: Theme.currentTheme.colors.textColor
                            text: usbCard.device
                                ? (usbCard.device.name || qsTr("U 盘"))
                                : qsTr("U 盘")
                        }
                        Text {
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                            font.pixelSize: Theme.currentTheme.typography.captionSize
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: usbCard.device
                                ? qsTr("剩余 %1").arg(usbCard.device.free || "?")
                                : qsTr("没有检测到")
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 4
                            radius: 2
                            visible: usbCard.device !== null && usbCard.percent > 0
                            color: Theme.currentTheme.colors.controlSecondaryColor

                            Rectangle {
                                height: parent.height
                                radius: parent.radius
                                width: parent.width
                                    * Math.min(100, Math.max(0, usbCard.percent)) / 100
                                color: Theme.currentTheme.colors.primaryColor

                                Behavior on width {
                                    NumberAnimation {
                                        duration: 260
                                        easing.type: Easing.OutCubic
                                    }
                                }
                            }
                        }
                    }
                }

                ToolTip.text: usbCard.device
                    ? qsTr("%1\n剩余 %2 / 共 %3 · %4 个分区")
                        .arg(usbCard.device.name || qsTr("U 盘"))
                        .arg(usbCard.device.free || "?")
                        .arg(usbCard.device.total || "?")
                        .arg(usbCard.device.partitions
                            ? usbCard.device.partitions.length : 1)
                    : qsTr("没有检测到 U 盘")
            }

            // 磁盘槽位：老配置遗留的 path 入口；U 盘由上面的固定卡片承接。
            Repeater {
                model: root.slots

                delegate: Frame {
                    id: diskCard

                    width: root.cardWidth
                    height: root.cardHeight
                    padding: 0
                    radius: Theme.currentTheme.appearance.windowRadius
                    border.width: 0
                    opacity: modelData.exists === false ? 0.55 : 1

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.slotActivated(modelData)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 10

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: modelData.icon || ""
                            iconSize: 24
                            tint: modelData.exists === false
                                ? Theme.currentTheme.colors.textSecondaryColor
                                : Theme.currentTheme.colors.textColor
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 2

                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                                font.weight: Font.DemiBold
                                color: Theme.currentTheme.colors.textColor
                                text: modelData.name || qsTr("磁盘")
                            }
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideMiddle
                                font.pixelSize: Theme.currentTheme.typography.captionSize
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: root.slotDetail(modelData)
                            }

                            // U 盘与磁盘都给出占用条；多分区容量由后端合并。
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                radius: 2
                                visible: modelData.exists !== false
                                    && Number(modelData.percent || 0) > 0
                                color: Theme.currentTheme.colors.controlSecondaryColor

                                Rectangle {
                                    height: parent.height
                                    radius: parent.radius
                                    width: parent.width
                                        * Math.min(100, Math.max(0,
                                            Number(modelData.percent || 0))) / 100
                                    color: Theme.currentTheme.colors.primaryColor

                                    Behavior on width {
                                        NumberAnimation {
                                            duration: 260
                                            easing.type: Easing.OutCubic
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
