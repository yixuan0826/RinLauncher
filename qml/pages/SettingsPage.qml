import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"
import "../dialogs"
import "settings"

// 设置页。左侧是可折叠的分类栏，右侧只渲染当前分类。
//
// 之前的「大标题 + 一条长滚动列表」在分类变多以后很难找东西；改成分栏之后，
// 每一类都是独立的一页，元素数量也跟着降下来了。
Item {
    id: settingsPage
    objectName: "settingsPage"

    property var model: ({})
    property var pending: ({})
    property var backupInfo: ({})

    // 读取配置时控件会跟着变。这个标记把「程序赋值」和「用户操作」区分开，
    // 免得一次重读把所有值又当成用户改动写回磁盘。
    property bool syncing: false

    readonly property var sections: [
        { key: "general", title: qsTr("通用"),
          description: qsTr("启动、热键、权限与日常维护"),
          icon: "ic_fluent_settings_20_regular" },
        { key: "personalization", title: qsTr("个性化"),
          description: qsTr("主题、强调色与窗口材质"),
          icon: "ic_fluent_paint_brush_20_regular" },
        { key: "update", title: qsTr("更新"),
          description: qsTr("更新通道、版本状态与发布说明"),
          icon: "ic_fluent_arrow_download_20_regular" },
        { key: "backup", title: qsTr("备份"),
          description: qsTr("手动备份与每 7 天的自动备份"),
          icon: "ic_fluent_save_20_regular" },
        { key: "about", title: qsTr("关于与鸣谢"),
          description: qsTr("版本、运行环境与开源致谢"),
          icon: "ic_fluent_info_20_regular" }
    ]

    property int currentIndex: 0
    property bool navCollapsed: false

    readonly property var updater: UpdateManager
    readonly property string updateState: updater ? updater.state : "idle"
    readonly property string updateMessage: updater ? updater.message : ""
    readonly property real updateProgress: updater ? updater.progress : 0
    readonly property bool updateBusy: updater ? updater.busy : false
    readonly property bool updateCanInstall: updater ? updater.canInstall : false
    readonly property string updateNotes: updater ? updater.releaseNotes : ""
    readonly property var updateNoteBlocks: updater ? updater.releaseNoteBlocks : []
    readonly property string updateReleaseUrl: updater ? updater.releaseUrl : ""
    readonly property string updateCurrentVersion: updater ? updater.currentVersion : ""
    readonly property string updateLatestVersion: updater ? updater.latestVersion : ""

    readonly property var activeSection: sections[Math.max(0,
        Math.min(currentIndex, sections.length - 1))]

    ConfirmDialog {
        id: confirmDialog
    }

    Timer {
        id: applyTimer
        interval: 350
        repeat: false
        onTriggered: settingsPage.flush()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ── 左侧分类栏 ────────────────────────────────────────────
        Rectangle {
            id: navRail
            Layout.fillHeight: true
            Layout.preferredWidth: settingsPage.navCollapsed ? 56 : 216
            color: "transparent"

            Behavior on Layout.preferredWidth {
                NumberAnimation {
                    duration: 180
                    easing.type: Easing.OutCubic
                }
            }

            Rectangle {
                width: 1
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                color: Theme.currentTheme.colors.dividerBorderColor
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 2

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 46
                    Layout.bottomMargin: 4

                    ToolButton {
                        width: 32
                        height: 32
                        anchors.verticalCenter: parent.verticalCenter
                        x: settingsPage.navCollapsed
                            ? (parent.width - width) / 2
                            : parent.width - width
                        icon.name: settingsPage.navCollapsed
                            ? "ic_fluent_panel_left_expand_20_regular"
                            : "ic_fluent_panel_left_contract_20_regular"
                        ToolTip.text: settingsPage.navCollapsed
                            ? qsTr("展开分类")
                            : qsTr("收起分类")
                        onClicked: settingsPage.navCollapsed = !settingsPage.navCollapsed
                    }
                }

                Repeater {
                    model: settingsPage.sections

                    delegate: Rectangle {
                        id: navRow

                        readonly property bool active:
                            settingsPage.currentIndex === index

                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        radius: Theme.currentTheme.appearance.smallRadius
                        color: navRow.active
                            ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                                      Theme.currentTheme.colors.primaryColor.g,
                                      Theme.currentTheme.colors.primaryColor.b,
                                      0.14)
                            : hoverHandler.hovered
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : "transparent"

                        Behavior on color {
                            ColorAnimation { duration: 120 }
                        }

                        Rectangle {
                            width: 3
                            height: 16
                            radius: 2
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            color: Theme.currentTheme.colors.primaryColor
                            visible: navRow.active
                        }

                        Icon {
                            anchors.centerIn: parent
                            visible: settingsPage.navCollapsed
                            name: modelData.icon
                            size: 18
                            color: navRow.active
                                ? Theme.currentTheme.colors.primaryColor
                                : Theme.currentTheme.colors.textSecondaryColor
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 10
                            visible: !settingsPage.navCollapsed
                            spacing: 12

                            Icon {
                                name: modelData.icon
                                size: 16
                                color: navRow.active
                                    ? Theme.currentTheme.colors.primaryColor
                                    : Theme.currentTheme.colors.textSecondaryColor
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.title
                                wrapMode: Text.NoWrap
                                elide: Text.ElideRight
                                color: navRow.active
                                    ? Theme.currentTheme.colors.textColor
                                    : Theme.currentTheme.colors.textSecondaryColor
                            }
                        }

                        ToolTip.visible: settingsPage.navCollapsed && hoverHandler.hovered
                        ToolTip.text: modelData.title
                        ToolTip.delay: 400

                        HoverHandler {
                            id: hoverHandler
                        }

                        TapHandler {
                            onTapped: settingsPage.currentIndex = index
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }

        // ── 右侧内容 ─────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 22
                Layout.bottomMargin: 8
                spacing: 2

                Text {
                    font.bold: true
                    font.pixelSize: 20
                    color: Theme.currentTheme.colors.textColor
                    text: settingsPage.activeSection.title
                }

                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: settingsPage.activeSection.description
                }
            }

            StackLayout {
                id: pageStack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: settingsPage.currentIndex

                GeneralSettingsPage {
                    id: generalPage
                    page: settingsPage
                }
                PersonalizationSettingsPage {
                    id: personalizationPage
                    page: settingsPage
                }
                UpdateSettingsPage {
                    id: updatePage
                    page: settingsPage
                }
                BackupSettingsPage {
                    id: backupPage
                    page: settingsPage
                }
                AboutSettingsPage {
                    id: aboutPage
                    page: settingsPage
                }
            }
        }
    }

    Component.onCompleted: {
        reloadSettings()
        reloadBackupInfo()
        selectSection(ConfigManager.takePendingSettingsSection
                      ? ConfigManager.takePendingSettingsSection() : "")
    }

    // 离开本页时把还没落盘的改动冲掉。
    Component.onDestruction: {
        applyTimer.stop()
        flush()
    }

    Connections {
        target: ConfigManager

        function onSettingsChanged() {
            if (Object.keys(settingsPage.pending).length === 0) {
                settingsPage.reloadSettings()
            }
        }

        function onBackupChanged() {
            settingsPage.reloadBackupInfo()
        }

        function onSettingsSectionRequested(name) {
            settingsPage.selectSection(name)
        }
    }

    function openPage(page) {
        // 页面够不到窗口对象，切页请求从后端转交给 main.py。
        ConfigManager.requestPage(page)
    }

    // 分类页共用一个确认弹窗；每个分类各养一个纯属浪费。
    function openConfirm(message, onAccepted) {
        confirmDialog.ask(message, onAccepted)
    }

    // 分类切换。兼容旧的「分组 id」写法（标题栏 / 托盘菜单还在用）。
    function selectSection(name) {
        var map = {
            "general": 0, "generalGroup": 0, "launcherGroup": 0,
            "hotkeyGroup": 0, "advancedGroup": 0,
            "personalization": 1, "appearanceGroup": 1,
            "update": 2, "updateGroup": 2,
            "backup": 3, "backupGroup": 3,
            "about": 4, "aboutGroup": 4
        }
        var index = map[String(name || "")]
        if (index !== undefined) {
            currentIndex = index
        }
    }

    function reloadSettings() {
        syncing = true
        model = ConfigManager.getSettings()
        generalPage.reload()
        personalizationPage.reload()
        updatePage.reload()
        backupPage.reload()
        aboutPage.reload()
        syncing = false
    }

    function reloadBackupInfo() {
        backupInfo = ConfigManager.getBackupInfo()
        backupPage.reload()
    }

    // 先攒进 pending，再由定时器合并写盘；主题这类要立刻看到效果的顺手就应用。
    function apply(key, value) {
        pending[key] = value
        applyTimer.restart()
        applyLive(key, value)
    }

    function flush() {
        if (Object.keys(pending).length === 0) {
            return
        }
        // 页面销毁 / 程序退出时定时器可能还欠着一拍，此时上下文已经开始拆了，
        // 拿不到 ConfigManager。丢掉这最后一拍没有副作用：下次进来还会重读配置。
        if (!ConfigManager) {
            return
        }
        var payload = pending
        pending = ({})
        ConfigManager.updateSettings(payload)
    }

    function applyLive(key, value) {
        switch (key) {
        case "theme":
            Theme.setTheme(value === "light" ? Theme.mode.Light
                          : value === "dark" ? Theme.mode.Dark
                          : Theme.mode.Auto)
            break
        case "accentColor":
            Theme.setThemeColor(value)
            break
        // 材质由后端应用：材质要碰原生窗口句柄，QML 这边碰不到，
        // 统一走 settingsChanged → main.apply_material。
        }
    }
}
