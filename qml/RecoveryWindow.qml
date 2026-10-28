import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "components"
import "dialogs"

// 恢复模式窗口。
//
// 独立于设置窗口：设置页加载不出来、配置被改坏、更新装出问题时，这个窗口
// 仍然能打开 —— 它只依赖 ConfigManager 的几个只读接口和最基本的文件操作。
//
// 入口：设置 → 存储 → 恢复；或带 --safe-mode / --diagnostic 启动。
FluentWindowBase {
    id: recoveryWindow

    width: 820
    height: 800
    minimumWidth: 700
    minimumHeight: 560
    title: qsTr("恢复模式")
    titleEnabled: true

    property var info: ({})
    property var backups: []

    readonly property bool inRecoveryMode: info.launchMode === "safe"
                                          || info.launchMode === "diagnostic"
    readonly property string modeLabel: info.launchMode === "safe"
        ? qsTr("安全模式")
        : info.launchMode === "diagnostic" ? qsTr("诊断模式") : qsTr("正常模式")

    // 启动动作：继续使用 / 安全模式 / 诊断模式。
    readonly property var launchActions: [
        { key: "continue", title: qsTr("继续使用"),
          description: qsTr("关掉这个窗口，回到桌面小窗"),
          icon: "ic_fluent_play_20_regular", danger: false },
        { key: "safe", title: qsTr("以安全模式重启"),
          description: qsTr("跳过全局热键、系统状态轮询与配置监听"),
          icon: "ic_fluent_shield_20_regular", danger: false },
        { key: "diagnostic", title: qsTr("以诊断模式重启"),
          description: qsTr("日志级别临时拉到 DEBUG，方便复现问题"),
          icon: "ic_fluent_bug_20_regular", danger: false }
    ]

    // 诊断与清理。
    readonly property var diagnoseActions: [
        { key: "logs", title: qsTr("打开日志目录"),
          description: qsTr("日志按天记录，最近 30 天会保留"),
          icon: "ic_fluent_folder_open_20_regular", danger: false },
        { key: "export", title: qsTr("导出日志"),
          description: qsTr("打包成 ZIP，方便发给开发者"),
          icon: "ic_fluent_arrow_download_20_regular", danger: false },
        { key: "copy", title: qsTr("复制诊断信息"),
          description: qsTr("版本、系统、数据目录与最近日志"),
          icon: "ic_fluent_copy_20_regular", danger: false },
        { key: "temp", title: qsTr("清除临时文件"),
          description: qsTr("删除下载的更新包与解包残留"),
          icon: "ic_fluent_broom_20_regular", danger: true }
    ]

    // 数据与版本。
    readonly property var dataActions: [
        { key: "restore", title: qsTr("恢复备份"),
          description: qsTr("最近的一份配置备份会覆盖当前配置"),
          icon: "ic_fluent_history_20_regular", danger: false },
        { key: "resetSettings", title: qsTr("重置应用设置"),
          description: qsTr("启动台和图标保留，设置项回到默认值"),
          icon: "ic_fluent_settings_20_regular", danger: true },
        { key: "resetAll", title: qsTr("重置全部配置"),
          description: qsTr("启动台一起清空，图标文件留在磁盘上"),
          icon: "ic_fluent_warning_20_regular", danger: true }
    ]

    function applyAccentColor() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var value = ConfigManager.accentColor
        if (value && value.length > 0) {
            Utils.primaryColor = value
        }
    }

    function reload() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        info = ConfigManager.getRecoveryInfo()
        backups = ConfigManager.listBackups()
    }

    function runAction(key) {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        switch (key) {
        case "continue":
            // 安全 / 诊断模式下「继续使用」= 正常重启，否则热键与轮询仍然关着。
            if (recoveryWindow.inRecoveryMode) {
                ConfigManager.restartWithMode("normal")
            } else {
                recoveryWindow.closeRequested()
                ConfigManager.requestPage("compact")
            }
            break
        case "safe":
            ConfigManager.restartWithMode("safe")
            break
        case "diagnostic":
            ConfigManager.restartWithMode("diagnostic")
            break
        case "logs":
            ConfigManager.openLogFolder()
            break
        case "export":
            ConfigManager.exportLogs()
            break
        case "copy":
            if (ConfigManager.copyDiagnostics()) {
                ConfigManager.notify(qsTr("诊断信息已复制"), "success")
            }
            break
        case "temp":
            confirmDialog.ask(qsTr("清除临时文件？下载中的更新包也会被删掉。"),
                              function () { ConfigManager.cleanTempFiles() })
            break
        case "restore":
            if (backups.length === 0) {
                ConfigManager.notify(qsTr("还没有可用的备份"), "warning")
                return
            }
            confirmDialog.ask(qsTr("用最近的备份 %1 覆盖当前配置？")
                              .arg(backups[0].name), function () {
                if (ConfigManager.restoreBackup(backups[0].name)) {
                    recoveryWindow.reload()
                }
            })
            break
        case "resetSettings":
            confirmDialog.ask(qsTr("重置应用设置？配置会先自动备份一份。"),
                              function () {
                ConfigManager.resetAppSettings()
                recoveryWindow.reload()
            })
            break
        case "resetAll":
            confirmDialog.ask(qsTr("重置全部配置？启动台槽位会被清空。"),
                              function () {
                ConfigManager.resetToDefaults()
                recoveryWindow.reload()
            })
            break
        }
    }

    Component.onCompleted: {
        applyAccentColor()
        reload()
    }

    // FluentWindowBase 的默认属性是 content（只收 Item），Connections 不能直接
    // 当子对象写；挂到属性上，信号一样能收到。
    property Connections accentWatcher: Connections {
        target: ConfigManager
        function onAccentColorChanged() { recoveryWindow.applyAccentColor() }
        function onConfigChanged() { recoveryWindow.applyAccentColor() }
    }

    property Connections dataWatcher: Connections {
        target: ConfigManager
        function onBackupChanged() { recoveryWindow.reload() }
        function onConfigChanged() { recoveryWindow.reload() }
    }

    signal closeRequested()

    onClosing: function (close) {
        close.accepted = false
        recoveryWindow.closeRequested()
    }

    ConfirmDialog {
        id: confirmDialog
    }

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
            width: Math.min(flick.width - 48, 760)
            spacing: 18

            // ── 标题区 ──────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 24
                spacing: 12

                AppIcon {
                    Layout.alignment: Qt.AlignVCenter
                    iconKey: "ic_fluent_shield_20_regular"
                    iconSize: 28
                    tint: Theme.currentTheme.colors.textColor
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        typography: Typography.Title
                        color: Theme.currentTheme.colors.textColor
                        text: qsTr("恢复模式")
                    }

                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("v%1 · %2 · %3")
                            .arg(recoveryWindow.info.version || "")
                            .arg(recoveryWindow.modeLabel)
                            .arg(recoveryWindow.info.configDir || "")
                    }
                }
            }

            // ── 模式提示 ────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                visible: recoveryWindow.inRecoveryMode
                implicitHeight: modeText.implicitHeight + 24
                radius: Theme.currentTheme.appearance.windowRadius
                color: Qt.rgba(Theme.currentTheme.colors.systemCautionColor.r,
                               Theme.currentTheme.colors.systemCautionColor.g,
                               Theme.currentTheme.colors.systemCautionColor.b,
                               0.12)

                Text {
                    id: modeText
                    anchors.fill: parent
                    anchors.margins: 12
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textColor
                    text: recoveryWindow.info.launchMode === "safe"
                        ? qsTr("当前处于安全模式：全局热键、系统状态轮询与配置监听都不会启动。确认问题解决后，请在「继续使用」里正常重启。")
                        : qsTr("当前处于诊断模式：日志级别已临时拉到 DEBUG。复现问题后，请导出日志并附在反馈里。")
                }
            }

            // ── 启动 ───────────────────────────────────────────────
            RecoveryGroup {
                Layout.fillWidth: true
                title: qsTr("启动")
                iconKey: "ic_fluent_play_20_regular"
                actions: recoveryWindow.launchActions
                onTriggered: function (key) { recoveryWindow.runAction(key) }
            }

            // ── 诊断与清理 ──────────────────────────────────────────
            RecoveryGroup {
                Layout.fillWidth: true
                title: qsTr("诊断与清理")
                iconKey: "ic_fluent_bug_20_regular"
                actions: recoveryWindow.diagnoseActions
                onTriggered: function (key) { recoveryWindow.runAction(key) }
            }

            // ── 数据与版本 ──────────────────────────────────────────
            RecoveryGroup {
                Layout.fillWidth: true
                title: qsTr("数据与版本")
                iconKey: "ic_fluent_database_20_regular"
                actions: recoveryWindow.dataActions
                onTriggered: function (key) { recoveryWindow.runAction(key) }
            }

            // ── 备份概况 ────────────────────────────────────────────
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                wrapMode: Text.Wrap
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: recoveryWindow.backups.length > 0
                    ? qsTr("共 %1 份配置备份，最近一份：%2（%3）")
                        .arg(recoveryWindow.backups.length)
                        .arg(recoveryWindow.backups[0].time)
                        .arg(recoveryWindow.backups[0].name)
                    : qsTr("还没有配置备份。重置类操作会先自动备份一份。")
            }

            Item { Layout.fillWidth: true; Layout.preferredHeight: 8 }
        }
    }
}
