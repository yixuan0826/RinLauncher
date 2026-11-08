import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 小窗第三行：存储位置卡 + 磁盘 / U 盘槽位卡。
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
    // 存储行槽位（row === 1）：U 盘、固定的硬盘。
    property var slots: []

    signal storageActivated()
    signal slotActivated(var slot)

    implicitHeight: 72
    readonly property int cardHeight: 66

    // 单卡铺开，两张平分，再多就固定宽度横向滚动。
    // 之前统一 202，两张卡（存储 + 一个磁盘）就会顶出可视区、还剩半截在滚动里。
    readonly property real cardWidth: {
        var count = 1 + root.slots.length
        if (count <= 1) {
            return Math.min(320, scroller.width)
        }
        return Math.max(160, Math.min(202,
            (scroller.width - (count - 1) * 8) / count))
    }

    function slotDetail(slot) {
        if (!slot) return ""
        if (slot.kind === "usb") {
            if (slot.exists === false) return qsTr("没有检测到")
            return qsTr("剩余 %1").arg(slot.free || "?")
        }
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
                    onClicked: root.storageActivated()
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

            // 磁盘槽位：U 盘与「指定的硬盘」是各自独立的两格。
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
