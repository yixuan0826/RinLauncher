import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 存储：日志、备份的占用与清理入口。
// 所有删除动作都先过 SettingsPage 的确认弹窗（page.openConfirm）。
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
                title: qsTr("日志")
                iconKey: "ic_fluent_document_text_20_regular"

                FormRow {
                    label: qsTr("最近 30 天")
                    description: qsTr("%1 个文件 · %2")
                        .arg(pageRoot.page.storageInfo.logCount || 0)
                        .arg(pageRoot.page.storageInfo.logSize || "0B")
                    Button {
                        text: qsTr("打开目录")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: ConfigManager.openLogFolder()
                    }
                    Button {
                        text: qsTr("导出 ZIP")
                        icon.name: "ic_fluent_arrow_download_20_regular"
                        onClicked: ConfigManager.exportLogs()
                    }
                }

                FormRow {
                    label: qsTr("清理日志")
                    description: qsTr("删除历史日志；今天正在写入的文件会保留")
                    Button {
                        text: qsTr("清理")
                        icon.name: "ic_fluent_delete_20_regular"
                        onClicked: pageRoot.page.openConfirm(
                            qsTr("删除历史日志？"), function () {
                                ConfigManager.clearLogs()
                                pageRoot.page.reloadStorageInfo()
                            })
                    }
                }
            }

            SettingsGroup {
                title: qsTr("备份")
                iconKey: "ic_fluent_save_20_regular"

                FormRow {
                    label: qsTr("备份占用")
                    description: qsTr("%1 份配置备份 · %2")
                        .arg(pageRoot.page.storageInfo.backupCount || 0)
                        .arg(pageRoot.page.storageInfo.backupSize || "0B")
                    Button {
                        text: qsTr("打开目录")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: ConfigManager.openBackupFolder()
                    }
                    Button {
                        text: qsTr("清空备份")
                        icon.name: "ic_fluent_delete_20_regular"
                        enabled: (pageRoot.page.storageInfo.backupCount || 0) > 0
                        onClicked: pageRoot.page.openConfirm(
                            qsTr("删除全部备份？手动备份也会被删掉。"), function () {
                                ConfigManager.clearBackups()
                                pageRoot.page.reloadBackupInfo()
                            })
                    }
                }
            }

            SettingsGroup {
                title: qsTr("恢复")
                iconKey: "ic_fluent_shield_20_regular"

                FormRow {
                    label: qsTr("恢复模式")
                    description: qsTr("安全 / 诊断模式重启、恢复备份、重置配置都在这里")
                    Item { Layout.fillWidth: true }
                    Button {
                        text: qsTr("打开恢复模式")
                        icon.name: "ic_fluent_open_20_regular"
                        onClicked: ConfigManager.requestPage("recovery")
                    }
                }
            }
        }
    }

    function reload() {
        // 数据来自 page.storageInfo 的绑定，这里只为保持各页统一接口。
    }
}
