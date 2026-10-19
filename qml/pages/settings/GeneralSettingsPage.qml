import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 通用：启动、热键、启动台入口、权限与日常维护。
Item {
    id: pageRoot

    property var page

    readonly property var startupModes: ["off", "normal", "admin"]
    property int startupPendingAttempts: 0

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
                title: qsTr("启动与热键")
                iconKey: "ic_fluent_power_20_regular"

                FormRow {
                    label: qsTr("启动方式")
                    description: qsTr("管理员自启动由任务计划实现")
                    ComboBox {
                        id: startupCombo
                        Layout.preferredWidth: 180
                        model: [qsTr("关闭"), qsTr("登录时启动"), qsTr("管理员自启动")]
                        onActivated: function (index) {
                            pageRoot.applyStartup(index)
                        }
                    }
                }

                FormRow {
                    label: qsTr("启动时最小化")
                    description: qsTr("启动后只留托盘")
                    Switch {
                        id: startMinimizedSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("startMinimized", checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("系统托盘图标")
                    description: qsTr("关闭后仅热键可用")
                    Switch {
                        id: traySwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("showTray", checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("显示 / 隐藏")
                    description: qsTr("任何程序里都能唤出小窗")
                    HotkeyField {
                        id: hotkeyField
                        Layout.preferredWidth: 260
                        onEdited: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("globalHotkey", sequence)
                        }
                    }
                    ToolButton {
                        icon.name: "ic_fluent_arrow_reset_20_regular"
                        ToolTip.text: qsTr("恢复默认热键")
                        onClicked: {
                            hotkeyField.value = "Ctrl+Space"
                            pageRoot.page.apply("globalHotkey", "Ctrl+Space")
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("热键需含修饰键（Ctrl / Alt / Shift / Win）；留空即关闭。")
                }
            }

            SettingsGroup {
                title: qsTr("启动台")
                iconKey: "ic_fluent_apps_20_regular"

                FormRow {
                    label: qsTr("编辑启动台")
                    description: qsTr("打开独立的启动台编辑窗口")
                    Button {
                        text: qsTr("打开编辑窗口")
                        icon.name: "ic_fluent_apps_20_regular"
                        onClicked: pageRoot.page.openPage("launcher")
                    }
                }

                FormRow {
                    label: qsTr("重新检测磁盘")
                    description: qsTr("插拔 U 盘 / 移动硬盘后手动刷新")
                    Button {
                        text: qsTr("刷新磁盘")
                        icon.name: "ic_fluent_arrow_sync_20_regular"
                        onClicked: ConfigManager.refreshStorageInfo()
                    }
                }
            }

            SettingsGroup {
                title: qsTr("权限与维护")
                iconKey: "ic_fluent_wrench_20_regular"

                FormRow {
                    label: qsTr("自动提权")
                    description: qsTr("关闭后管理员动作会被拦下")
                    Switch {
                        id: elevateSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("adminAutoElevate", checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("提权前确认")
                    Switch {
                        id: confirmAdminSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("confirmAdminActions", checked)
                        }
                    }
                }

                FormRow {
                    label: qsTr("日志级别")
                    description: qsTr("重启后生效")
                    ComboBox {
                        id: logCombo
                        Layout.preferredWidth: 160
                        model: ["DEBUG", "INFO", "WARNING", "ERROR"]
                        onActivated: function (index) {
                            pageRoot.page.apply(
                                "logLevel",
                                ["DEBUG", "INFO", "WARNING", "ERROR"][index])
                        }
                    }
                }

                FormRow {
                    label: qsTr("配置文件")
                    description: qsTr("导入 / 导出 YAML")
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("打开目录")
                            icon.name: "ic_fluent_folder_open_20_regular"
                            onClicked: ConfigManager.openConfigFolder()
                        }
                        Button {
                            text: qsTr("导入")
                            icon.name: "ic_fluent_arrow_import_20_regular"
                            onClicked: ConfigManager.importConfig()
                        }
                        Button {
                            text: qsTr("导出")
                            icon.name: "ic_fluent_arrow_export_20_regular"
                            onClicked: ConfigManager.exportConfig()
                        }
                        ToolButton {
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            ToolTip.text: qsTr("从磁盘重读配置")
                            onClicked: ConfigManager.reloadConfig()
                        }
                    }
                }

                FormRow {
                    label: qsTr("重启程序")
                    description: qsTr("提权重启会弹一次 UAC")
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("重启")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            onClicked: ConfigManager.restartApplication()
                        }
                        Button {
                            text: qsTr("提权重启")
                            icon.name: "ic_fluent_shield_20_regular"
                            onClicked: ConfigManager.restartAsAdmin()
                        }
                    }
                }

                FormRow {
                    label: qsTr("恢复默认")
                    description: qsTr("重置全部配置，不可撤销")
                    Button {
                        text: qsTr("重置")
                        icon.name: "ic_fluent_arrow_reset_20_regular"
                        onClicked: pageRoot.confirmReset()
                    }
                }
            }
        }
    }

    function confirmReset() {
        // ConfirmDialog 在设置页根部，一页一份，避免每个分类各养一个弹窗。
        pageRoot.page.openConfirm(
            qsTr("这会清空当前的全部分区、条目、槽位与设置，并恢复出厂默认值。确定继续吗？"),
            function () { ConfigManager.resetToDefaults() })
    }

    function reload() {
        var model = page.model
        startMinimizedSwitch.checked = model.startMinimized === true
        traySwitch.checked = model.showTray !== false
        hotkeyField.value = model.globalHotkey || ""
        elevateSwitch.checked = model.adminAutoElevate !== false
        confirmAdminSwitch.checked = model.confirmAdminActions !== false
        logCombo.currentIndex = Math.max(0,
            ["DEBUG", "INFO", "WARNING", "ERROR"].indexOf(model.logLevel || "INFO"))
        reloadStartup()
    }

    // ── 启动方式（三态）────────────────────────────────
    function applyStartup(index) {
        var result = ConfigManager.setStartupMode(startupModes[index])
        if (!result) {
            reloadStartup()
            return
        }
        if (result.pending) {
            // 提权进程还没回来（用户可能正对着 UAC 思考）：定时回查系统里的真实状态。
            startupPendingAttempts = 15
            startupPollTimer.restart()
        } else {
            reloadStartup()
        }
    }

    function reloadStartup() {
        var info = ConfigManager.getStartupState()
        startupCombo.currentIndex = Math.max(0, startupModes.indexOf(info.state))
    }

    onVisibleChanged: {
        if (visible) {
            reloadStartup()
        }
    }

    // 轮询只负责「叫人去刷」：真正的读取发生在后台线程，刷完经
    // startupStateChanged 回来再更新界面 —— 全程不阻塞 UI。
    Timer {
        id: startupPollTimer
        interval: 2000
        repeat: true
        onTriggered: {
            pageRoot.startupPendingAttempts -= 1
            if (pageRoot.startupPendingAttempts <= 0) {
                startupPollTimer.stop()
                startupFinalTimer.restart()
            }
            ConfigManager.refreshStartupState()
        }
    }

    // 轮询次数用尽后的兜底复检：等最后一次异步刷新回来再判定成败。
    Timer {
        id: startupFinalTimer
        interval: 1500
        onTriggered: {
            var info = ConfigManager.getStartupState()
            if (info.state !== info.mode) {
                ConfigManager.notify(qsTr("启动方式没有生效（授权可能被取消了）"), "warning")
            }
            pageRoot.reloadStartup()
        }
    }

    Connections {
        target: ConfigManager

        function onStartupStateChanged() {
            if (!pageRoot.visible) {
                return
            }
            var info = ConfigManager.getStartupState()
            if (pageRoot.startupPendingAttempts > 0 && info.state === info.mode) {
                // 提权后的状态就位：收工，顺便把下拉同步到真实值。
                pageRoot.startupPendingAttempts = 0
                startupPollTimer.stop()
            }
            pageRoot.reloadStartup()
        }
    }
}
