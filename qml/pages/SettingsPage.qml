import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"
import "../dialogs"

// 设置。
//
// 结构上做了一次整理：
//   * 顶部一排锚点，点一下直接跳到对应分组，不用一路滚；
//   * 材质从「亚克力开关」换成 RinUI 的材质下拉（默认增强云母），
//     小窗的亚克力是独立的一项（它是桌面挂件，不跟完整窗口共用材质）；
//   * 「关于」搬到独立页面，这里只留配置。
// 所有改动都是即时生效的：控件先写进 pending，再由 350ms 的定时器合并写盘，
// 拖动滑杆或在输入框里连续打字都不会把配置文件刷爆。
Item {
    id: settingsPage

    property var model: ({})
    property var pending: ({})

    // 锚点：（标题，图标，分组 id）
    readonly property var sections: [
        {"title": qsTr("常规"), "icon": "ic_fluent_home_20_regular", "target": "generalGroup"},
        {"title": qsTr("外观"), "icon": "lawnicons:generic_gallery", "target": "appearanceGroup"},
        {"title": qsTr("启动台"), "icon": "ic_fluent_apps_20_regular", "target": "launcherGroup"},
        {"title": qsTr("热键"), "icon": "ic_fluent_keyboard_20_regular", "target": "hotkeyGroup"},
        {"title": qsTr("高级"), "icon": "ic_fluent_toolbox_20_regular", "target": "advancedGroup"}
    ]

    ConfirmDialog {
        id: confirmDialog
    }

    // 右上角「…」菜单：分组跳转 + 打开配置目录，头部只留一个入口。
    Menu {
        id: sectionsMenu

        objectName: "sectionsMenu"
        position: Position.None

        Repeater {
            model: settingsPage.sections

            delegate: MenuItem {
                text: modelData.title
                icon.name: modelData.icon
                onTriggered: settingsPage.scrollTo(modelData.target)
            }
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("打开配置目录")
            icon.name: "ic_fluent_folder_open_20_regular"
            onTriggered: ConfigManager.openConfigFolder()
        }
    }

    Timer {
        id: applyTimer
        interval: 350
        repeat: false
        onTriggered: settingsPage.flush()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            spacing: 8

            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 0
                Text {
                    font.bold: true
                    font.pixelSize: Theme.currentTheme.typography.bodySize + 4
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("设置")
                }
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("改完立即生效")
                }
            }

            Item { Layout.fillWidth: true }

            // 分组跳转收进右上角的「…」菜单，头部只留这一个入口。
            ToolButton {
                id: sectionsButton
                objectName: "sectionsButton"
                Layout.alignment: Qt.AlignVCenter
                icon.name: "ic_fluent_more_horizontal_20_regular"
                ToolTip.text: qsTr("更多")
                ToolTip.visible: hovered
                ToolTip.delay: 500
                onClicked: settingsPage.popupSectionsMenu(sectionsButton)
            }
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: contentColumn.implicitHeight + 28
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: contentColumn
                x: 16
                width: scroller.width - 32
                spacing: 16

                // ── 常规 ──
                SettingsGroup {
                    id: generalGroup
                    title: qsTr("常规")
                    iconKey: "ic_fluent_home_20_regular"

                    FormRow {
                        label: qsTr("开机自动启动")
                        description: qsTr("登录时自动启动（写注册表）")
                        Switch {
                            id: autoStartSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("autoStart", checked)
                        }
                    }

                    FormRow {
                        label: qsTr("启动时最小化")
                        description: qsTr("启动后不弹小窗，只留托盘")
                        Switch {
                            id: startMinimizedSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("startMinimized", checked)
                        }
                    }

                    FormRow {
                        label: qsTr("系统托盘图标")
                        description: qsTr("关掉后只能用热键唤出小窗")
                        Switch {
                            id: traySwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("showTray", checked)
                        }
                    }
                }

                // ── 外观 ──
                SettingsGroup {
                    id: appearanceGroup
                    title: qsTr("外观")
                    iconKey: "lawnicons:generic_gallery"

                    FormRow {
                        label: qsTr("主题模式")
                        ComboBox {
                            id: themeCombo
                            Layout.preferredWidth: 180
                            model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]
                            onActivated: function (index) {
                                settingsPage.apply("theme",
                                                   ["system", "light", "dark"][index])
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("强调色")
                        DropDownColorPicker {
                            id: accentPicker
                            Layout.preferredWidth: 180
                            onColorChanged: settingsPage.apply("accentColor", color.toString())
                        }
                        ToolButton {
                            icon.name: "ic_fluent_arrow_reset_20_regular"
                            ToolTip.text: qsTr("恢复默认强调色")
                            onClicked: {
                                accentPicker.color = "#0078d4"
                                settingsPage.apply("accentColor", "#0078d4")
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("窗口材质")
                        description: qsTr("默认增强云母，不支持时自动回退")
                        ComboBox {
                            id: materialCombo
                            Layout.preferredWidth: 180
                            model: [qsTr("增强云母"), qsTr("云母"), qsTr("不透明")]
                            onActivated: function (index) {
                                settingsPage.apply("material",
                                                   ["tabbed", "mica", "none"][index])
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("小窗亚克力")
                        description: qsTr("小窗单独用亚克力，比云母更透")
                        Switch {
                            id: acrylicSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("compactAcrylic", checked)
                        }
                    }

                    FormRow {
                        label: qsTr("动画效果")
                        description: qsTr("关闭后过渡动画立即完成")
                        Switch {
                            id: animationSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("animationEnabled", checked)
                        }
                    }
                }

                // ── 启动台 ──
                SettingsGroup {
                    id: launcherGroup
                    title: qsTr("启动台")
                    iconKey: "ic_fluent_apps_20_regular"

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("面板内容在「启动台」页里配，这里只管行为。")
                    }

                    FormRow {
                        label: qsTr("打开面板")
                        description: qsTr("去调整面板格子")
                        Button {
                            text: qsTr("启动台设置")
                            icon.name: "ic_fluent_apps_20_regular"
                            onClicked: settingsPage.openPage("launcher")
                        }
                    }

                    FormRow {
                        label: qsTr("重新检测")
                        description: qsTr("插拔磁盘后手动刷新容量")
                        Button {
                            text: qsTr("刷新磁盘")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            onClicked: ConfigManager.refreshStorageInfo()
                        }
                    }
                }

                // ── 热键 ──
                SettingsGroup {
                    id: hotkeyGroup
                    title: qsTr("热键")
                    iconKey: "lawnicons:generic_keyboard"

                    FormRow {
                        label: qsTr("显示 / 隐藏")
                        description: qsTr("任何程序里都能唤出小窗")
                        HotkeyField {
                            id: hotkeyField
                            Layout.preferredWidth: 260
                            onEdited: settingsPage.apply("globalHotkey", sequence)
                        }
                        ToolButton {
                            icon.name: "ic_fluent_arrow_reset_20_regular"
                            ToolTip.text: qsTr("恢复默认热键")
                            onClicked: {
                                hotkeyField.value = "Ctrl+Space"
                                settingsPage.apply("globalHotkey", "Ctrl+Space")
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("必须带一个修饰键（Ctrl / Alt / Shift / Win）；留空关闭热键。")
                    }
                }

                // ── 高级 ──
                SettingsGroup {
                    id: advancedGroup
                    title: qsTr("高级")
                    iconKey: "ic_fluent_toolbox_20_regular"

                    FormRow {
                        label: qsTr("自动提权")
                        description: qsTr("管理员格直接弹 UAC")
                        Switch {
                            id: elevateSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("adminAutoElevate", checked)
                        }
                    }

                    FormRow {
                        label: qsTr("提权前确认")
                        description: qsTr("提权前先确认一次")
                        Switch {
                            id: confirmAdminSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            onCheckedChanged: settingsPage.apply("confirmAdminActions", checked)
                        }
                    }

                    FormRow {
                        label: qsTr("日志级别")
                        description: qsTr("重启后生效（配置目录 launcher.log）")
                        ComboBox {
                            id: logCombo
                            Layout.preferredWidth: 180
                            model: ["DEBUG", "INFO", "WARNING", "ERROR"]
                            onActivated: function (index) {
                                settingsPage.apply(
                                    "logLevel",
                                    ["DEBUG", "INFO", "WARNING", "ERROR"][index])
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("配置")
                        description: qsTr("打开配置目录 / 文件，或整份导入导出")
                        RowLayout {
                            spacing: 8
                            Button {
                                text: qsTr("目录")
                                icon.name: "ic_fluent_folder_open_20_regular"
                                onClicked: ConfigManager.openConfigFolder()
                            }
                            Button {
                                text: qsTr("文件")
                                icon.name: "ic_fluent_document_20_regular"
                                onClicked: ConfigManager.openConfigFile()
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
                        }
                    }

                    FormRow {
                        label: qsTr("图标库")
                        description: qsTr("导入的图标和从程序提取的图标")
                        RowLayout {
                            spacing: 8
                            Button {
                                text: qsTr("打开图标目录")
                                icon.name: "ic_fluent_image_20_regular"
                                onClicked: ConfigManager.openIconFolder()
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("以管理员重启")
                        description: qsTr("以管理员身份重启（托盘可能消失）")
                        Button {
                            text: qsTr("立即重启")
                            icon.name: "ic_fluent_shield_20_regular"
                            onClicked: ConfigManager.restartAsAdmin()
                        }
                    }

                    FormRow {
                        label: qsTr("恢复默认")
                        description: qsTr("重置全部配置，不可撤销")
                        Button {
                            text: qsTr("重置")
                            icon.name: "ic_fluent_arrow_reset_20_regular"
                            onClicked: confirmDialog.ask(
                                qsTr("这会清空当前的全部分区、条目、槽位与设置，并恢复出厂默认值。确定继续吗？"),
                                function () { ConfigManager.resetToDefaults() })
                        }
                    }
                }

                // ── 关于入口 ──
                SettingsGroup {
                    title: qsTr("关于")
                    iconKey: "ic_fluent_info_20_regular"

                    FormRow {
                        label: qsTr("Rin Launcher")
                        description: qsTr("基于 RinUI（PySide6 + QML）")
                        Button {
                            text: qsTr("打开关于页")
                            icon.name: "ic_fluent_info_20_regular"
                            onClicked: settingsPage.openPage("about")
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: reloadSettings()

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
    }

    function openPage(page) {
        // 页面够不到窗口对象，切页请求从后端转交给 main.py。
        ConfigManager.requestPage(page)
    }

    function scrollTo(targetId) {
        // 分组对象没法用字符串索引，这里显式映射一次，省掉 eval 之类的花招。
        var map = {
            "generalGroup": generalGroup,
            "appearanceGroup": appearanceGroup,
            "launcherGroup": launcherGroup,
            "hotkeyGroup": hotkeyGroup,
            "advancedGroup": advancedGroup
        }
        var group = map[targetId]
        if (group) {
            scroller.contentY = Math.max(0, group.y - 8)
        }
    }

    // 「…」菜单贴在按钮左下方弹出（与主窗口标题栏的「…」同一套定位）。
    function popupSectionsMenu(anchor) {
        // 页面根是普通 Item，`settingsPage.window` 在 Qt 6 下拿不到东西；
        // 把按钮角点映射到页面坐标系后直接 popup（弹出层的 parent 就是本页）。
        var point = anchor.mapToItem(settingsPage, anchor.width, anchor.height + 4)
        sectionsMenu.popup(Qt.point(Math.max(0, point.x - sectionsMenu.width), point.y))
    }

    function reloadSettings() {
        model = ConfigManager.getSettings()

        autoStartSwitch.checked = model.autoStart === true
        startMinimizedSwitch.checked = model.startMinimized === true
        traySwitch.checked = model.showTray !== false

        themeCombo.currentIndex = Math.max(0, ["system", "light", "dark"].indexOf(model.theme))
        accentPicker.color = model.accentColor || "#0078d4"
        materialCombo.currentIndex = Math.max(0,
            ["tabbed", "mica", "none"].indexOf(model.material || "tabbed"))
        acrylicSwitch.checked = model.compactAcrylic !== false
        animationSwitch.checked = model.animationEnabled !== false

        hotkeyField.value = model.globalHotkey || ""

        elevateSwitch.checked = model.adminAutoElevate !== false
        confirmAdminSwitch.checked = model.confirmAdminActions !== false
        logCombo.currentIndex = Math.max(0,
            ["DEBUG", "INFO", "WARNING", "ERROR"].indexOf(model.logLevel || "INFO"))
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
        // 材质由后端应用：小窗亚克力与完整窗口的云母都要碰原生窗口句柄，
        // QML 这边碰不到，统一走 settingsChanged → main.apply_material/apply_compact_acrylic。
        }
    }
}
