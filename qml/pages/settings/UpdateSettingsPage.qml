import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 更新：顶部版本栏负责检查 / 下载 / 安装，页面底部单独负责回滚。
// 回滚不再依赖 old.zip：在底部旧版本列表里选一个低于当前版本的 Release 重装。
Item {
    id: pageRoot

    property var page

    readonly property var mirrorNames: ["github", "ghfast", "ghproxy"]
    readonly property var speedResults: pageRoot.page && pageRoot.page.updater
        ? pageRoot.page.updater.mirrorSpeeds : []
    readonly property bool speedTesting: pageRoot.page && pageRoot.page.updater
        ? pageRoot.page.updater.speedTesting : false
    readonly property var updater: pageRoot.page ? pageRoot.page.updater : null

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

            // 顶部版本栏：版本号 + 更新状态 + 检查 / 下载 / 安装。
            // 回滚是独立流程，放在页面最底部，不复用这里的版本选择。
            Frame {
                Layout.fillWidth: true
                implicitHeight: topColumn.implicitHeight + 32
                radius: Theme.currentTheme.appearance.windowRadius

                ColumnLayout {
                    id: topColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 16
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 24

                        ColumnLayout {
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 2
                            Text {
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: qsTr("当前版本")
                            }
                            Text {
                                typography: Typography.Title
                                color: Theme.currentTheme.colors.textColor
                                text: "v" + pageRoot.page.updateCurrentVersion
                            }
                        }

                        ColumnLayout {
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 2
                            Text {
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: qsTr("最新版本")
                            }
                            Text {
                                typography: Typography.Title
                                color: Theme.currentTheme.colors.textColor
                                text: pageRoot.page.updateLatestVersion.length > 0
                                    ? "v" + pageRoot.page.updateLatestVersion : "—"
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            Layout.maximumWidth: 420
                            wrapMode: Text.Wrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                            color: pageRoot.page.updateState === "error"
                                ? Theme.currentTheme.colors.systemCriticalColor
                                : Theme.currentTheme.colors.textSecondaryColor
                            text: pageRoot.page.updateMessage
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: qsTr("检查更新")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.checkNow()
                        }
                        Button {
                            text: qsTr("下载更新")
                            icon.name: "ic_fluent_arrow_download_20_regular"
                            highlighted: pageRoot.updater
                                ? pageRoot.updater.canDownload : false
                            enabled: pageRoot.updater
                                ? pageRoot.updater.canDownload : false
                            onClicked: pageRoot.downloadNow()
                        }
                        Button {
                            text: pageRoot.updater
                                && pageRoot.updater.downloadedVersion.length > 0
                                ? qsTr("安装 v%1").arg(pageRoot.updater.downloadedVersion)
                                : qsTr("安装")
                            icon.name: "ic_fluent_checkmark_circle_20_regular"
                            visible: pageRoot.page.updateCanInstall
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.installNow()
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: qsTr("打开下载目录")
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

                    ProgressBar {
                        Layout.fillWidth: true
                        visible: pageRoot.page.updateState === "downloading"
                        value: pageRoot.page.updateProgress
                        from: 0
                        to: 1
                    }
                }
            }

            SettingsGroup {
                title: qsTr("更新设置")
                iconKey: "ic_fluent_arrow_download_20_regular"

                FormRow {
                    label: qsTr("自动提醒通道")
                    description: qsTr("只影响自动检查时的提示；下面列表里始终包含全部版本")
                    RinComboBox {
                        id: channelCombo
                        Layout.preferredWidth: 220
                        model: [qsTr("仅正式版"), qsTr("包含预发布")]
                        onActivated: function (index) {
                            if (!pageRoot.page.updater) return
                            pageRoot.page.updater.setChannel(
                                index === 0 ? "stable" : "prerelease")
                        }
                    }
                }

                FormRow {
                    label: qsTr("启动时检查")
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

                FormRow {
                    label: qsTr("更新源")
                    RinComboBox {
                        id: mirrorCombo
                        Layout.preferredWidth: 160
                        model: ["GitHub", "ghfast", "ghproxy"]
                        onActivated: function (index) {
                            if (!pageRoot.page || !pageRoot.page.updater) return
                            pageRoot.page.updater.setMirror(pageRoot.mirrorNames[index])
                        }
                    }
                    Button {
                        text: pageRoot.speedTesting ? qsTr("测速中…") : qsTr("测速并自动选择")
                        icon.name: "ic_fluent_flash_20_regular"
                        enabled: !pageRoot.speedTesting
                        onClicked: {
                            if (pageRoot.page && pageRoot.page.updater) {
                                pageRoot.page.updater.testMirrors()
                            }
                        }
                    }
                }

                FormRow {
                    label: qsTr("自动选择最快")
                    Switch {
                        id: mirrorAutoSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            if (!pageRoot.page.updater) return
                            pageRoot.page.updater.setMirrorAuto(checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("测速结果")
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Repeater {
                            model: pageRoot.speedResults

                            delegate: Text {
                                color: modelData.ok
                                    ? Theme.currentTheme.colors.textColor
                                    : Theme.currentTheme.colors.textSecondaryColor
                                text: modelData.ok
                                    ? qsTr("%1 · %2 ms").arg(modelData.label).arg(modelData.ms)
                                    : qsTr("%1 · 超时").arg(modelData.label)
                            }
                        }

                        Text {
                            visible: pageRoot.speedResults.length === 0
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("尚未测速")
                        }
                    }
                }
            }

            SettingsGroup {
                title: qsTr("安装完整性")
                iconKey: "ic_fluent_wrench_screwdriver_20_regular"

                FormRow {
                    label: qsTr("安装清单")
                    description: pageRoot.updater
                        ? (pageRoot.updater.installationStatus
                           || qsTr("检查程序文件是否与 install-manifest.json 一致"))
                        : ""
                    Button {
                        text: qsTr("检查")
                        icon.name: "ic_fluent_checkmark_circle_20_regular"
                        onClicked: {
                            if (pageRoot.updater) {
                                pageRoot.updater.checkInstallation()
                            }
                        }
                    }
                    Button {
                        text: qsTr("修复安装（回滚）")
                        icon.name: "ic_fluent_arrow_reset_20_regular"
                        enabled: pageRoot.updater ? pageRoot.updater.canRepair : false
                        onClicked: {
                            if (!pageRoot.updater) return
                            pageRoot.page.openConfirm(
                                qsTr("退出程序并用更新前备份覆盖当前程序文件？data 目录不会被改动。"),
                                function () { pageRoot.updater.repairInstallation() })
                        }
                    }
                }
            }

            SettingsGroup {
                title: qsTr("高级：从文件安装")
                iconKey: "ic_fluent_folder_zip_20_regular"

                FormRow {
                    label: qsTr("本地安装包")
                    description: qsTr("不推荐：仅在在线下载不可用时使用，选自己下载的 RinLauncher.zip")
                    Button {
                        text: qsTr("选择本地 zip…")
                        icon.name: "ic_fluent_arrow_upload_20_regular"
                        enabled: !pageRoot.page.updateBusy
                        onClicked: {
                            if (pageRoot.page && pageRoot.page.updater) {
                                pageRoot.page.updater.installFromFile()
                            }
                        }
                    }
                    Button {
                        text: qsTr("重启到恢复模式")
                        icon.name: "ic_fluent_arrow_sync_20_regular"
                        onClicked: ConfigManager.restartWithMode("recovery")
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
                                    radius: Theme.currentTheme.appearance.smallRadius
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
                            text: qsTr("暂无更新说明")
                        }
                    }
                }
            }
            SettingsGroup {
                title: qsTr("回滚到旧版本")
                iconKey: "ic_fluent_arrow_undo_20_regular"

                FormRow {
                    label: qsTr("旧版本")
                    description: qsTr("只列出低于当前版本的 Release；下载安装后 data/ 会保留")
                    RinComboBox {
                        id: rollbackCombo
                        Layout.fillWidth: true
                        Layout.maximumWidth: 420
                        model: pageRoot.updater ? pageRoot.updater.rollbackLabels : []
                        currentIndex: pageRoot.updater ? pageRoot.updater.rollbackIndex : -1
                        enabled: pageRoot.updater
                                 && pageRoot.updater.rollbackLabels.length > 0
                                 && !pageRoot.page.updateBusy
                        onActivated: function (index) {
                            if (pageRoot.updater) {
                                pageRoot.updater.selectRollback(index)
                            }
                        }
                    }
                    Button {
                        text: qsTr("刷新列表")
                        icon.name: "ic_fluent_arrow_sync_20_regular"
                        enabled: !pageRoot.page.updateBusy
                        onClicked: pageRoot.checkNow()
                    }
                }

                FormRow {
                    label: qsTr("操作")
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Button {
                            text: qsTr("下载旧版本")
                            icon.name: "ic_fluent_arrow_download_20_regular"
                            highlighted: pageRoot.updater
                                ? pageRoot.updater.canDownloadRollback : false
                            enabled: pageRoot.updater
                                ? pageRoot.updater.canDownloadRollback : false
                            onClicked: pageRoot.downloadRollbackNow()
                        }
                        Button {
                            text: pageRoot.updater
                                && pageRoot.updater.downloadedVersion.length > 0
                                ? qsTr("安装 v%1").arg(pageRoot.updater.downloadedVersion)
                                : qsTr("安装")
                            icon.name: "ic_fluent_checkmark_circle_20_regular"
                            visible: pageRoot.page.updateCanInstall
                                && pageRoot.updater
                                && pageRoot.updater.downloadedVersion
                                   === (pageRoot.updater.rollbackRelease.version || "")
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.installNow()
                        }
                        Button {
                            text: qsTr("打开 Release")
                            icon.name: "ic_fluent_open_20_regular"
                            visible: pageRoot.updater
                                && pageRoot.updater.rollbackUrl.length > 0
                            onClicked: pageRoot.openRollbackRelease()
                        }
                    }
                }

                FormRow {
                    label: qsTr("回滚说明")
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: pageRoot.updater && pageRoot.updater.rollbackNotes.length > 0
                            ? pageRoot.updater.rollbackNotes
                            : qsTr("选择旧版本后显示说明")
                    }
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
        if (page.updater && page.updater.downloadedVersion.length > 0) {
            page.openConfirm(
                qsTr("安装 v%1？程序会退出，替换文件后自动重启。").arg(
                    page.updater.downloadedVersion),
                function () { page.updater.installUpdate() })
        }
    }

    function downloadNow() {
        if (page.updater) {
            page.updater.downloadSelected()
        }
    }

    function downloadRollbackNow() {
        if (page.updater) {
            page.updater.downloadRollback()
        }
    }

    function openRollbackRelease() {
        if (page.updater) {
            page.updater.openRollbackPage()
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
        mirrorCombo.currentIndex = Math.max(0,
            pageRoot.mirrorNames.indexOf(model.updateMirror || "github"))
        mirrorAutoSwitch.checked = model.updateMirrorAuto !== false
    }

}
