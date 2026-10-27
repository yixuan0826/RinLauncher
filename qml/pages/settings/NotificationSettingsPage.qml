import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 通知：功能类别 × 投递渠道。
//
// 写盘走 ConfigManager.setNotificationChannel()，和设置项那套「攒一批再写」
// 分开：通知开关是立刻生效的小布尔值，没必要为它多一个 debounce。
Item {
    id: pageRoot

    property var page
    property var info: ({})

    // 类别 / 渠道由后端给，避免两边各写一份中文名。
    readonly property var categories: info.categories || []
    readonly property var channels: info.channels || []

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: content.implicitHeight + 48
        ScrollBar.vertical: ScrollBar {}

        ColumnLayout {
            id: content
            x: Math.max(24, (flick.width - width) / 2)
            width: Math.min(flick.width - 48, 860)
            spacing: 18

            SettingsGroup {
                title: qsTr("通知分类")
                iconKey: "ic_fluent_alert_20_regular"

                FormRow {
                    label: qsTr("怎么通知")
                    description: qsTr("每一类通知可以分别选择投递渠道；错误与警告一定会显示应用内提示。")
                }

                Repeater {
                    model: pageRoot.categories

                    delegate: Item {
                        id: row

                        required property var modelData

                        Layout.fillWidth: true
                        implicitHeight: inner.implicitHeight + 8

                        ColumnLayout {
                            id: inner
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6

                            Text {
                                Layout.fillWidth: true
                                color: Theme.currentTheme.colors.textColor
                                text: row.modelData.label
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 18

                                Repeater {
                                    model: pageRoot.channels

                                    delegate: CheckBox {
                                        required property var modelData

                                        // Windows 通知在非 Windows 上不可用。
                                        enabled: modelData.key !== "native"
                                                 || pageRoot.info.nativeAvailable !== false
                                        text: modelData.label
                                        checked: {
                                            var values = row.modelData.channels || {}
                                            return values[modelData.key] === true
                                        }
                                        onToggled: ConfigManager.setNotificationChannel(
                                            row.modelData.key, modelData.key, checked)
                                    }
                                }

                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }

            SettingsGroup {
                title: qsTr("说明")
                iconKey: "ic_fluent_info_20_regular"

                FormRow {
                    label: qsTr("应用内提示")
                    description: qsTr("小窗底部弹出的轻提示，始终可用")
                }

                FormRow {
                    label: qsTr("托盘气泡")
                    description: qsTr("系统托盘的通知气泡；托盘关闭时自动跳过")
                }

                FormRow {
                    label: qsTr("Windows 通知")
                    description: qsTr("操作中心里的原生通知，走系统免打扰规则")
                }
            }
        }
    }

    function reload() {
        info = ConfigManager.getNotificationSettings()
    }

    Connections {
        target: ConfigManager

        function onNotificationsChanged() {
            pageRoot.reload()
        }
    }
}
