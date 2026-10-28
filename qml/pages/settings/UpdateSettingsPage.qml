import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 更新：版本列表、下载、安装，以及选中版本的更新说明（Markdown）。
//
// 回滚不再依赖 old.zip：在「版本列表」里选一个旧一点的版本重装就行。
Item {
    id: pageRoot

    property var page

    readonly property var mirrorNames: ["github", "ghfast", "ghproxy"]
    readonly property var speedResults: pageRoot.page && pageRoot.page.updater
        ? pageRoot.page.updater.mirrorSpeeds : []
    readonly property bool speedTesting: pageRoot.page && pageRoot.page.updater
        ? pageRoot.page.updater.speedTesting : false
    readonly property var updater: pageRoot.page ? pageRoot.page.updater : null
    readonly property var releaseLabels: updater ? updater.releaseLabels : []

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
                    label: qsTr("自动提醒通道")
                    description: qsTr("只影响自动检查时的提示；下面列表里始终包含全部版本")
                    ComboBox {
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
                    ComboBox {
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
                        text: qsTr("恢复模式")
                        icon.name: "ic_fluent_shield_20_regular"
                        onClicked: ConfigManager.requestPage("recovery")
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

                // 版本列表：选旧版本就是「在线回滚」。
                FormRow {
                    label: qsTr("版本列表")
                    description: qsTr("下载并安装任意版本；装回旧版本就是回滚")
                    ComboBox {
                        id: releaseCombo
                        Layout.fillWidth: true
                        Layout.maximumWidth: 420
                        model: pageRoot.releaseLabels
                        currentIndex: pageRoot.updater ? pageRoot.updater.selectedIndex : -1
                        enabled: pageRoot.releaseLabels.length > 0
                                       && !pageRoot.page.updateBusy
                        onActivated: function (index) {
                            if (pageRoot.updater) {
                                pageRoot.updater.selectRelease(index)
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

                // 安装包校验：GitHub API 给了 digest 才能比，没给就直说。
                FormRow {
                    label: qsTr("安装包校验")
                    visible: pageRoot.page.updateState === "ready"
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: pageRoot.page.updater && pageRoot.page.updater.digestVerified
                            ? Theme.currentTheme.colors.textColor
                            : Theme.currentTheme.colors.systemCautionColor
                        text: pageRoot.page.updater && pageRoot.page.updater.digestVerified
                            ? qsTr("sha256 校验通过")
                            : qsTr("Release 未提供 digest，本次只能靠 HTTPS 与解包校验")
                    }
                }

                // 失败原因：不只是一句「失败了」，把脚本给出的原文摆出来。
                FormRow {
                    label: qsTr("错误详情")
                    visible: pageRoot.updater && pageRoot.updater.lastError.length > 0
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.systemCriticalColor
                        text: pageRoot.updater ? pageRoot.updater.lastError : ""
                    }
                    ToolButton {
                        icon.name: "ic_fluent_clipboard_20_regular"
                        ToolTip.text: qsTr("复制错误详情")
                        onClicked: {
                            if (pageRoot.updater) {
                                ConfigManager.copyText(pageRoot.updater.lastError)
                            }
                        }
                    }
                }

                FormRow {
                    label: qsTr("操作")
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: qsTr("下载所选版本")
                            icon.name: "ic_fluent_arrow_download_20_regular"
                            highlighted: pageRoot.updater ? pageRoot.updater.canDownload : false
                            enabled: pageRoot.updater ? pageRoot.updater.canDownload : false
                            onClicked: pageRoot.downloadNow()
                        }

                        Button {
                            text: pageRoot.page.updateCanInstall
                                ? qsTr("安装 v%1").arg(pageRoot.updater.downloadedVersion)
                                : qsTr("安装")
                            icon.name: "ic_fluent_checkmark_circle_20_regular"
                            visible: pageRoot.page.updateCanInstall
                            enabled: !pageRoot.page.updateBusy
                            onClicked: pageRoot.installNow()
                        }

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

    // 后端选中项变了（刷新列表 / 默认选中新版本）时，下拉跟着走。
    Connections {
        target: pageRoot.updater

        function onChanged() {
            var index = pageRoot.updater ? pageRoot.updater.selectedIndex : -1
            if (releaseCombo.currentIndex !== index) {
                releaseCombo.currentIndex = index
            }
        }
    }
}
