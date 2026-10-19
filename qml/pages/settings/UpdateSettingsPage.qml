import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 更新：通道、状态、操作，以及最新 Release 的更新说明（Markdown）。
Item {
    id: pageRoot

    property var page

    Flickable {
        id: flick
        objectName: "updateSettingsFlick"
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
                title: qsTr("更新设置")
                iconKey: "ic_fluent_arrow_download_20_regular"

                FormRow {
                    label: qsTr("更新通道")
                    description: qsTr("稳定版取 GitHub Latest；测试版取最新 Pre-Release")
                    ComboBox {
                        id: channelCombo
                        Layout.preferredWidth: 220
                        model: [qsTr("稳定版（Latest）"), qsTr("测试版（Pre-Release）")]
                        onActivated: function (index) {
                            if (!pageRoot.page.updater) return
                            pageRoot.page.updater.setChannel(
                                index === 0 ? "stable" : "prerelease")
                        }
                    }
                }

                FormRow {
                    label: qsTr("启动时检查")
                    description: qsTr("发现新版本会自动下载，安装前会再提示")
                    Switch {
                        id: autoCheckSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            if (!pageRoot.page.updater) return
                            pageRoot.page.updater.setAutoCheck(checked)
                        }
                    }
                }
            }

            SettingsGroup {
                title: qsTr("版本与状态")
                iconKey: "ic_fluent_history_20_regular"

                FormRow {
                    label: qsTr("当前版本")
                    Text {
                        color: Theme.currentTheme.colors.textColor
                        text: "v" + pageRoot.page.updateCurrentVersion
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        visible: pageRoot.page.updateLatestVersion.length > 0
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("最新：v%1").arg(pageRoot.page.updateLatestVersion)
                    }
                }

                FormRow {
                    label: qsTr("状态")
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: pageRoot.page.updateState === "error"
                                ? Theme.currentTheme.colors.systemCriticalColor
                                : Theme.currentTheme.colors.textColor
                            text: pageRoot.page.updateMessage
                        }

                        ProgressBar {
                            Layout.fillWidth: true
                            visible: pageRoot.page.updateState === "downloading"
                            value: pageRoot.page.updateProgress
                            from: 0
                            to: 1
                        }
                    }
                }

                FormRow {
                    label: qsTr("操作")
                    RowLayout {
                        spacing: 8

                        Button {
                            text: qsTr("检查更新")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.checkNow()
                        }

                        Button {
                            text: qsTr("安装并重启")
                            icon.name: "ic_fluent_arrow_download_20_regular"
                            highlighted: pageRoot.page.updateCanInstall
                            visible: pageRoot.page.updateCanInstall
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.installNow()
                        }

                        Button {
                            text: qsTr("下载目录")
                            icon.name: "ic_fluent_folder_open_20_regular"
                            onClicked: pageRoot.openDownloadFolder()
                        }

                        Button {
                            text: qsTr("打开 Release")
                            icon.name: "ic_fluent_open_20_regular"
                            visible: pageRoot.page.updateReleaseUrl.length > 0
                            onClicked: pageRoot.openRelease()
                        }
                    }
                }
            }

            SettingsGroup {
                title: qsTr("更新说明")
                iconKey: "ic_fluent_document_text_20_regular"

                // 说明直接铺开，交给外层设置页滚动 —— 双 Flickable 抢滚轮很难受。
                // Release 正文由后端拆成块（标题 / 段落 / 列表 / 引用 / 代码），
                // 每块一个 Text：Qt 的 Text.MarkdownText 在“先空后填”时会压扁行距。
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: notesColumn.implicitHeight + 28
                    radius: Theme.currentTheme.appearance.smallRadius
                    color: Theme.currentTheme.colors.cardColor
                    border.width: 1
                    border.color: Theme.currentTheme.colors.cardBorderColor

                    ColumnLayout {
                        id: notesColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 0

                        Repeater {
                            model: pageRoot.page.updateNoteBlocks

                            delegate: Item {
                                id: block

                                readonly property string kind: modelData.kind || "paragraph"
                                readonly property int level: modelData.level || 0
                                readonly property int size: kind === "heading"
                                    ? (level <= 1 ? 20 : level === 2 ? 16 : 15)
                                    : kind === "code" ? 12 : 14

                                Layout.fillWidth: true
                                Layout.preferredHeight: kind === "rule"
                                    ? 1 + (modelData.spaceBefore || 0)
                                    : Math.max(1, blockText.implicitHeight)
                                      + (modelData.spaceBefore || 0)
                                      + (kind === "code" ? 12 : 0)

                                Rectangle {
                                    visible: block.kind === "rule"
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.topMargin: modelData.spaceBefore || 0
                                    height: 1
                                    color: Theme.currentTheme.colors.dividerBorderColor
                                }

                                Rectangle {
                                    visible: block.kind === "code"
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.topMargin: modelData.spaceBefore || 0
                                    height: blockText.implicitHeight + 12
                                    radius: 4
                                    color: Theme.currentTheme.isDark
                                        ? Qt.rgba(1, 1, 1, 0.06)
                                        : Qt.rgba(0, 0, 0, 0.04)
                                }

                                Text {
                                    id: blockText
                                    visible: block.kind !== "rule"
                                    x: block.kind === "code" ? 10
                                        : (block.kind === "quote"
                                           || block.kind === "bullet"
                                           || block.kind === "ordered") ? 4 : 0
                                    y: (modelData.spaceBefore || 0)
                                        + (block.kind === "code" ? 6 : 0)
                                    width: parent.width - x
                                        - (block.kind === "code" ? 10 : 0)
                                    textFormat: Text.RichText
                                    text: modelData.html || ""
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.25
                                    lineHeightMode: Text.ProportionalHeight
                                    font.family: block.kind === "code"
                                        ? "Consolas" : Utils.fontFamily
                                    font.pixelSize: block.size
                                    font.bold: block.kind === "heading"
                                    font.italic: block.kind === "quote"
                                    color: block.kind === "quote"
                                        ? Theme.currentTheme.colors.textSecondaryColor
                                        : Theme.currentTheme.colors.textColor
                                    linkColor: Theme.currentTheme.colors.primaryColor
                                    onLinkActivated: function (link) {
                                        Qt.openUrlExternally(link)
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: pageRoot.page.updateNoteBlocks.length === 0
                            wrapMode: Text.Wrap
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("检查更新后，这里会显示最新 Release 的更新说明。")
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("内容来自 GitHub Release 正文（支持标题、列表、引用、代码块与链接）。")
                }
            }
        }
    }

    function checkNow() {
        if (page.updater) {
            page.updater.checkForUpdates()
        }
    }

    function installNow() {
        if (page.updater) {
            page.updater.installUpdate()
        }
    }

    function openRelease() {
        if (page.updater) {
            page.updater.openReleasePage()
        }
    }

    function openDownloadFolder() {
        if (page.updater) {
            page.updater.openDownloadFolder()
        }
    }

    function reload() {
        var model = page.model
        channelCombo.currentIndex = model.updateChannel === "prerelease" ? 1 : 0
        autoCheckSwitch.checked = model.autoCheckUpdates !== false
    }
}
