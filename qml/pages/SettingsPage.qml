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
    property var backups: []
    property var storageInfo: ({})

    // 读取配置时控件会跟着变。这个标记把「程序赋值」和「用户操作」区分开，
    // 免得一次重读把所有值又当成用户改动写回磁盘。
    property bool syncing: false

    readonly property var sections: [
        { key: "general", title: qsTr("通用"),
          icon: "ic_fluent_settings_20_regular" },
        { key: "personalization", title: qsTr("个性化"),
          icon: "ic_fluent_paint_brush_20_regular" },
        { key: "notification", title: qsTr("通知"),
          icon: "ic_fluent_alert_20_regular" },
        { key: "update", title: qsTr("更新"),
          icon: "ic_fluent_arrow_download_20_regular" },
        { key: "backup", title: qsTr("备份"),
          icon: "ic_fluent_save_20_regular" },
        { key: "storage", title: qsTr("存储"),
          icon: "ic_fluent_database_20_regular" },
        { key: "about", title: qsTr("关于与鸣谢"),
          icon: "ic_fluent_info_20_regular" }
    ]

    property int currentIndex: 0
    property bool navCollapsed: false

    readonly property string appVersion: ConfigManager
        ? String(ConfigManager.getRuntimeInfo().version || "") : ""

    readonly property var updater: UpdateManager
    readonly property string updateState: updater ? updater.state : "idle"
    readonly property string updateMessage: updater ? updater.message : ""
    readonly property real updateProgress: updater ? updater.progress : 0
    readonly property bool updateBusy: updater ? updater.busy : false
    readonly property bool updateCanInstall: updater ? updater.canInstall : false
    readonly property var updateNoteBlocks: updater ? updater.releaseNoteBlocks : []
    readonly property string updateReleaseUrl: updater ? updater.releaseUrl : ""
    readonly property string updateCurrentVersion: updater ? updater.currentVersion : ""
    readonly property string updateLatestVersion: updater ? updater.latestVersion : ""

    readonly property var activeSection: sections[Math.max(0,
        Math.min(currentIndex, sections.length - 1))]

    // 确认弹窗是独立顶层窗口，不能进窗口的 content（那是 Item 列表），用属性承载。
    property ConfirmDialog confirmDialog: ConfirmDialog {}

    RinToast {
        id: toast
    }

    Connections {
        target: ConfigManager

        function onShowToast(message, severity) {
            toast.show(message, severity)
        }
    }

    Timer {
        id: applyTimer
        interval: 350
        repeat: false
        onTriggered: settingsPage.flush()
    }

    // WinUI 3 NavigationView 的尺寸约定：展开 280 / 折叠 48。
    // 页面内所有分类页用同一套左右留白，标题和卡片因此能严格对齐。
    readonly property int navExpandedWidth: 280
    readonly property int navCompactWidth: 48
    readonly property real contentWidth: Math.max(
        280, Math.min(settingsPage.width - navPane.width - 48, 860))
    readonly property real contentX: Math.max(
        24, (settingsPage.width - navPane.width - contentWidth) / 2)

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ── 左侧分类栏（WinUI NavigationView）────────────────────
        Rectangle {
            id: navPane
            objectName: "settingsNavPane"
            Layout.fillHeight: true
            Layout.preferredWidth: settingsPage.navCollapsed
                ? settingsPage.navCompactWidth
                : settingsPage.navExpandedWidth
            color: Theme.currentTheme.colors.layerColor

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
                spacing: 0

                // 汉堡按钮：展开时常驻左上角，折叠后仍留在同一位置。
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48

                    ToolButton {
                        objectName: "settingsNavToggle"
                        width: 40
                        height: 40
                        x: 4
                        anchors.verticalCenter: parent.verticalCenter
                        icon.name: "ic_fluent_navigation_20_regular"
                        ToolTip.text: settingsPage.navCollapsed
                            ? qsTr("展开分类")
                            : qsTr("收起分类")
                        ToolTip.delay: 400
                        onClicked: settingsPage.navCollapsed = !settingsPage.navCollapsed
                    }
                }

                // 导航项：40px 高、图标 20、文字与图标间距 16、左侧强调条。
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    spacing: 2

                    Repeater {
                        model: settingsPage.sections

                        delegate: Item {
                            id: navRow

                            readonly property bool active:
                                settingsPage.currentIndex === index

                            Layout.fillWidth: true
                            Layout.preferredHeight: 40

                            Rectangle {
                                id: navPill
                                x: 4
                                width: parent.width - 8
                                height: 36
                                anchors.verticalCenter: parent.verticalCenter
                                radius: 4
                                color: navRow.active
                                    ? Qt.rgba(
                                        Theme.currentTheme.colors.primaryColor.r,
                                        Theme.currentTheme.colors.primaryColor.g,
                                        Theme.currentTheme.colors.primaryColor.b,
                                        0.14)
                                    : hoverHandler.hovered
                                        ? Theme.currentTheme.colors.subtleSecondaryColor
                                        : "transparent"

                                Behavior on color {
                                    ColorAnimation { duration: 120 }
                                }
                            }

                            Rectangle {
                                width: 3
                                height: 16
                                radius: 1.5
                                x: 0
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.currentTheme.colors.primaryColor
                                visible: navRow.active
                            }

                            Icon {
                                x: settingsPage.navCollapsed
                                    ? (parent.width - width) / 2
                                    : 16
                                anchors.verticalCenter: parent.verticalCenter
                                name: modelData.icon
                                size: 20
                                color: navRow.active
                                    ? Theme.currentTheme.colors.textColor
                                    : Theme.currentTheme.colors.textSecondaryColor
                            }

                            Text {
                                visible: !settingsPage.navCollapsed
                                x: 48
                                width: parent.width - 60
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.title
                                wrapMode: Text.NoWrap
                                elide: Text.ElideRight
                                color: navRow.active
                                    ? Theme.currentTheme.colors.textColor
                                    : Theme.currentTheme.colors.textSecondaryColor
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
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    Layout.bottomMargin: 16
                    visible: !settingsPage.navCollapsed
                    elide: Text.ElideRight
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("Rin Launcher v%1").arg(settingsPage.appVersion)
                }
            }
        }

        // ── 右侧内容 ─────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // 与分类页内部的 Flickable 用同一套宽度公式，标题不再偏 8px。
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 76

                Text {
                    x: settingsPage.contentX
                    width: settingsPage.contentWidth
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 18
                    typography: Typography.Title
                    color: Theme.currentTheme.colors.textColor
                    text: settingsPage.activeSection.title
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
                NotificationSettingsPage {
                    id: notificationPage
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
                StorageSettingsPage {
                    id: storagePage
                    page: settingsPage
                }
                AboutSettingsPage {
                    id: aboutPage
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
            "notification": 2, "notificationGroup": 2,
            "update": 3, "updateGroup": 3,
            "backup": 4, "backupGroup": 4,
            "storage": 5, "storageGroup": 5,
            "about": 6, "aboutGroup": 6
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
        notificationPage.reload()
        updatePage.reload()
        backupPage.reload()
        aboutPage.reload()
        syncing = false
    }

    function reloadBackupInfo() {
        backupInfo = ConfigManager.getBackupInfo()
        backups = ConfigManager.listBackups()
        backupPage.reload()
        reloadStorageInfo()
    }

    function reloadStorageInfo() {
        storageInfo = ConfigManager.getStorageUsage()
        storagePage.reload()
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
            // 只改当前引擎的 Utils 单例：强调色以 config.yaml 为准，其余窗口
            // 由 ConfigManager.accentColorChanged 同步；不走 Theme.setThemeColor，
            // 免得拖动颜色选择器时每帧都往 RinUI 的配置文件里写一次。
            Utils.primaryColor = value
            break
        case "accentColorMode":
            if (value === "system") {
                var systemColor = ConfigManager.systemAccentColor()
                if (systemColor && systemColor.length > 0) {
                    Utils.primaryColor = systemColor
                }
            }
            break
        }
    }
}
