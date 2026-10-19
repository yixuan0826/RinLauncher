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
                    label: qsTr("自动备份")
                    description: qsTr("每 7 天一次，保留 %1 份")
                        .arg(pageRoot.page.backupInfo.autoKeep || 8)
                    Text {
                        Layout.fillWidth: true
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: pageRoot.page.backupInfo.autoTime
                            ? qsTr("上次：%1（共 %2 份）")
                                .arg(pageRoot.page.backupInfo.autoTime)
                                .arg(pageRoot.page.backupInfo.autoCount)
                            : qsTr("还没有自动备份")
                    }
                    Button {
                        text: qsTr("打开备份目录")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: ConfigManager.openBackupFolder()
                    }
                }

                FormRow {
                    label: qsTr("手动备份")
                    Text {
                        Layout.fillWidth: true
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: pageRoot.page.backupInfo.manualTime
                            ? qsTr("上次：%1（共 %2 份）")
                                .arg(pageRoot.page.backupInfo.manualTime)
                                .arg(pageRoot.page.backupInfo.manualCount)
                            : qsTr("还没有手动备份")
                    }
                    Button {
                        text: qsTr("立即备份")
                        icon.name: "ic_fluent_save_20_regular"
                        onClicked: ConfigManager.backupNow()
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
    }
}
