import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 备份：7 天自动备份 + 不会被自动清理的手动备份。
Item {
    id: pageRoot

    property var page

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
                title: qsTr("配置备份")
                iconKey: "ic_fluent_save_20_regular"

                FormRow {
                    label: qsTr("启用自动备份")
                    description: qsTr("按下面的间隔自动备份，关闭后仍可手动备份")
                    Switch {
                        id: autoBackupSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        checked: pageRoot.page.backupInfo.autoEnabled !== false
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("autoBackupEnabled", checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("自动备份间隔")
                    description: qsTr("距上一份自动备份超过这个天数就补一份")
                    ComboBox {
                        id: intervalCombo
                        Layout.preferredWidth: 140
                        model: [qsTr("每天"), qsTr("3 天"), qsTr("7 天"),
                                qsTr("14 天"), qsTr("30 天")]
                        onActivated: function (index) {
                            pageRoot.page.apply(
                                "autoBackupIntervalDays", [1, 3, 7, 14, 30][index])
                        }
                    }
                }

                FormRow {
                    label: qsTr("自动备份上限")
                    description: qsTr("达到上限后覆盖最旧的自动备份；手动备份不受影响")
                    ComboBox {
                        id: keepCombo
                        Layout.preferredWidth: 140
                        model: [qsTr("4 份"), qsTr("8 份"), qsTr("16 份"), qsTr("32 份")]
                        onActivated: function (index) {
                            pageRoot.page.apply(
                                "autoBackupKeep", [4, 8, 16, 32][index])
                        }
                    }
                }

                FormRow {
                    label: qsTr("自动备份")
                    description: pageRoot.page.backupInfo.autoTime
                        ? qsTr("上次：%1（共 %2 份）")
                            .arg(pageRoot.page.backupInfo.autoTime)
                            .arg(pageRoot.page.backupInfo.autoCount)
                        : qsTr("还没有自动备份")
                    Button {
                        text: qsTr("打开备份目录")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: ConfigManager.openBackupFolder()
                    }
                }

                FormRow {
                    label: qsTr("手动备份")
                    description: pageRoot.page.backupInfo.manualTime
                        ? qsTr("上次：%1（共 %2 份）")
                            .arg(pageRoot.page.backupInfo.manualTime)
                            .arg(pageRoot.page.backupInfo.manualCount)
                        : qsTr("还没有手动备份")
                    Button {
                        text: qsTr("立即备份")
                        icon.name: "ic_fluent_save_20_regular"
                        onClicked: ConfigManager.backupNow()
                    }
                }
            }

            SettingsGroup {
                title: qsTr("备份文件")
                iconKey: "ic_fluent_history_20_regular"

                Text {
                    Layout.fillWidth: true
                    visible: pageRoot.page.backups.length === 0
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("还没有备份")
                }

                Repeater {
                    model: pageRoot.page.backups

                    delegate: FormRow {
                        label: (modelData.manual ? qsTr("手动") : qsTr("自动"))
                            + " · " + modelData.time
                        description: modelData.size
                        Button {
                            text: qsTr("恢复")
                            onClicked: pageRoot.page.openConfirm(
                                qsTr("用这份备份覆盖当前配置？会先把当前配置存一份手动备份。"),
                                function () {
                                    ConfigManager.restoreBackup(modelData.name)
                                    pageRoot.page.reloadBackupInfo()
                                })
                        }
                        ToolButton {
                            icon.name: "ic_fluent_delete_20_regular"
                            ToolTip.text: qsTr("删除这份备份")
                            onClicked: pageRoot.page.openConfirm(
                                qsTr("删除这份备份？"), function () {
                                    ConfigManager.deleteBackup(modelData.name)
                                    pageRoot.page.reloadBackupInfo()
                                })
                        }
                    }
                }

                FormRow {
                    label: qsTr("备份位置")
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.NoWrap
                        elide: Text.ElideMiddle
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: pageRoot.page.backupInfo.dir || "-"
                    }
                    ToolButton {
                        icon.name: "ic_fluent_folder_open_20_regular"
                        ToolTip.text: qsTr("打开备份目录")
                        onClicked: ConfigManager.openBackupFolder()
                    }
                }
            }
        }
    }

    function reload() {
        // 数据都在 page.backupInfo 上，绑定会自己刷新；这里只是为了和另外几页保持同一套接口。
        var intervals = [1, 3, 7, 14, 30]
        var keeps = [4, 8, 16, 32]
        intervalCombo.currentIndex = Math.max(0,
            intervals.indexOf(pageRoot.page.backupInfo.intervalDays))
        keepCombo.currentIndex = Math.max(0,
            keeps.indexOf(pageRoot.page.backupInfo.keepCount))
        autoBackupSwitch.checked = pageRoot.page.backupInfo.autoEnabled !== false
    }
}
