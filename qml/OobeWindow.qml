import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "components"
import "dialogs"

// 首次启动引导（OOBE）。
//
// 三步：认识启动台 → 基本设置 → 完成。设置项只保留第一次真正需要决定的几项，
// 其余都留在设置窗口里。完成后由后端把 appmodset.conf 的 first-run 写回 false。
FluentWindowBase {
    id: oobe

    width: 900
    height: 680
    minimumWidth: 760
    minimumHeight: 600
    title: qsTr("欢迎使用 Rin Launcher")
    titleEnabled: true

    property int step: 0
    readonly property int lastStep: 2
    property var model: ({})
    property bool saving: false
    // 用户在这一页选的形态，与第二页的「启动台形态」共用。
    property string pendingMode: "normal"

    signal closeRequested()

    function applyAccentColor() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) return
        var value = ConfigManager.accentColor
        if (value && value.length > 0) {
            Utils.primaryColor = value
        }
    }

    function reloadControls() {
        themeCombo.currentIndex = Math.max(0,
            ["system", "light", "dark"].indexOf(model.theme || "system"))
        tileCombo.currentIndex = Math.max(0,
            ["small", "medium", "large"].indexOf(model.tileSize || "medium"))
        animationSwitch.checked = model.animationEnabled !== false
        minimizeSwitch.checked = model.startMinimized === true
        arrowSwitch.checked = model.shortcutArrowGlobal !== false
        pendingMode = model.compactMode === "mini" ? "mini" : "normal"
        modeCombo.currentIndex = pendingMode === "mini" ? 1 : 0
        startupSwitch.checked = (model.startupMode || "off") !== "off"
    }

    Component.onCompleted: {
        applyAccentColor()
        model = ConfigManager.getSettings()
        reloadControls()
    }

    // 确认弹窗是独立顶层窗口，不能进窗口的 content（那是 Item 列表），用属性承载。
    property ConfirmDialog confirmReset: ConfirmDialog {}

    property Connections accentWatcher: Connections {
        target: ConfigManager
        function onAccentColorChanged() { oobe.applyAccentColor() }
        function onConfigChanged() { oobe.applyAccentColor() }
    }

    onClosing: function (close) {
        close.accepted = false
        // 关窗不等于完成：用户可以从设置里再次打开，first-run 仍然保留。
        oobe.closeRequested()
    }

    function finish(skip) {
        saving = true
        var payload = skip ? ({}) : ({
            "theme": ["system", "light", "dark"][themeCombo.currentIndex],
            "tileSize": ["small", "medium", "large"][tileCombo.currentIndex],
            "startMinimized": minimizeSwitch.checked,
            "animationEnabled": animationSwitch.checked,
            "shortcutArrowGlobal": arrowSwitch.checked,
            "compactMode": oobe.pendingMode,
            "startupMode": startupSwitch.checked ? "normal" : "off"
        })
        ConfigManager.completeOobe(payload)
        saving = false
        oobe.closeRequested()
        ConfigManager.requestPage("compact")
    }

    Flickable {
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: content.implicitHeight + 48
        ScrollBar.vertical: ScrollBar {}

        ColumnLayout {
            id: content
            x: Math.max(24, (parent.width - width) / 2)
            width: Math.min(parent.width - 48, 760)
            spacing: 18

            // ── 步骤指示 ──
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 24
                spacing: 8

                Repeater {
                    model: 3
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 4
                        radius: 2
                        color: index <= oobe.step
                            ? Theme.currentTheme.colors.primaryColor
                            : Theme.currentTheme.colors.controlSecondaryColor
                    }
                }
            }

            // ── 第一步：认识启动台 ──
            ColumnLayout {
                Layout.fillWidth: true
                visible: oobe.step === 0
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    spacing: 16

                    AppIcon {
                        iconKey: "url:" + Qt.resolvedUrl("../assets/icon.png")
                        iconSize: 64
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            typography: Typography.TitleLarge
                            color: Theme.currentTheme.colors.textColor
                            text: qsTr("欢迎使用 Rin Launcher")
                        }
                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            typography: Typography.Body
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("一个常驻桌面的启动台。先选一种形态，之后随时可以在「更多」菜单里切换。")
                        }
                    }
                }

                Repeater {
                    model: [
                        { mode: "normal", icon: "ic_fluent_apps_20_regular",
                          title: qsTr("完整启动台"),
                          text: qsTr("贴在主屏右下角：固定应用、存储位置与系统控制都在这一块。") },
                        { mode: "mini", icon: "ic_fluent_dock_row_20_regular",
                          title: qsTr("迷你模式"),
                          text: qsTr("收成单行工具条：常驻应用、存储与 U 盘开关，占地方最小。") }
                    ]
                    delegate: Frame {
                        id: modeCard
                        Layout.fillWidth: true
                        implicitHeight: 92
                        radius: Theme.currentTheme.appearance.windowRadius
                        readonly property bool chosen: oobe.pendingMode === modelData.mode
                        // 选中的那一张用强调色描边，右上角给个勾。
                        border.width: chosen ? 2 : 1
                        border.color: chosen
                            ? Theme.currentTheme.colors.primaryColor
                            : Theme.currentTheme.colors.windowBorderColor

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: oobe.pendingMode = modelData.mode
                        }

                        AppIcon {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            z: 2
                            visible: modeCard.chosen
                            iconKey: "ic_fluent_checkmark_circle_20_filled"
                            iconSize: 18
                            tint: Theme.currentTheme.colors.primaryColor
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            anchors.rightMargin: 36
                            spacing: 14

                            AppIcon {
                                Layout.alignment: Qt.AlignVCenter
                                iconKey: modelData.icon
                                iconSize: 28
                                tint: Theme.currentTheme.colors.textColor
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 3
                                Text {
                                    typography: Typography.BodyStrong
                                    color: Theme.currentTheme.colors.textColor
                                    text: modelData.title
                                }
                                Text {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.text
                                }
                            }
                        }
                    }
                }
            }

            // ── 第二步：基本设置 ──
            ColumnLayout {
                Layout.fillWidth: true
                visible: oobe.step === 1
                spacing: 12

                Text {
                    typography: Typography.TitleLarge
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("先调成你顺手的样子")
                }

                SettingsGroup {
                    title: qsTr("外观")
                    iconKey: "ic_fluent_paint_brush_20_regular"

                    FormRow {
                        label: qsTr("主题")
                        RinComboBox {
                            id: themeCombo
                            Layout.preferredWidth: 180
                            model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]
                            Component.onCompleted: currentIndex = Math.max(0,
                                ["system", "light", "dark"].indexOf(oobe.model.theme || "system"))
                            onActivated: function (index) {
                                Theme.setTheme(index === 1 ? Theme.mode.Light
                                              : index === 2 ? Theme.mode.Dark
                                              : Theme.mode.Auto)
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("磁贴尺寸")
                        RinComboBox {
                            id: tileCombo
                            Layout.preferredWidth: 180
                            model: [qsTr("小"), qsTr("中"), qsTr("大")]
                            Component.onCompleted: currentIndex = Math.max(0,
                                ["small", "medium", "large"].indexOf(oobe.model.tileSize || "medium"))
                        }
                    }

                    FormRow {
                        label: qsTr("动画效果")
                        Switch {
                            id: animationSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            checked: oobe.model.animationEnabled !== false
                        }
                    }
                }

                SettingsGroup {
                    title: qsTr("启动与系统")
                    iconKey: "ic_fluent_settings_20_regular"

                    FormRow {
                        label: qsTr("启动台形态")
                        description: qsTr("之后可以在「更多」菜单里随时切换")
                        RinComboBox {
                            id: modeCombo
                            Layout.preferredWidth: 180
                            model: [qsTr("完整启动台"), qsTr("迷你模式")]
                            onActivated: function (index) {
                                oobe.pendingMode = ["normal", "mini"][index]
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("开机自动启动")
                        description: qsTr("登录 Windows 后自动打开启动台")
                        Switch {
                            id: startupSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                        }
                    }

                    FormRow {
                        label: qsTr("启动时最小化")
                        description: qsTr("登录后只留托盘图标；需要时按热键唤出")
                        Switch {
                            id: minimizeSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            checked: oobe.model.startMinimized === true
                        }
                    }

                    FormRow {
                        label: qsTr("隐藏快捷方式小箭头")
                        description: qsTr("修改当前用户注册表，重启资源管理器后生效")
                        Switch {
                            id: arrowSwitch
                            checkedText: qsTr("开")
                            uncheckedText: qsTr("关")
                            checked: oobe.model.shortcutArrowGlobal !== false
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("更多选项（热键、通知、备份、更新通道）可以在设置窗口里调整。")
                }
            }

            // ── 第三步：完成 ──
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignHCenter
                visible: oobe.step === 2
                spacing: 12

                Item { Layout.preferredHeight: 40 }

                AppIcon {
                    Layout.alignment: Qt.AlignHCenter
                    iconKey: "ic_fluent_checkmark_circle_20_filled"
                    iconSize: 56
                    tint: Theme.currentTheme.colors.systemSuccessColor
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    typography: Typography.Title
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("准备好了")
                }

                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("启动台会出现在主屏右下角。右键任意一格可以编辑，标题栏的「…」里可以切换形态与设置。")
                }

                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("形态：%1 ｜ 主题：%2 ｜ 磁贴：%3 ｜ 开机自启：%4")
                        .arg(oobe.pendingMode === "mini" ? qsTr("迷你模式") : qsTr("完整启动台"))
                        .arg([qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")][themeCombo.currentIndex])
                        .arg([qsTr("小"), qsTr("中"), qsTr("大")][tileCombo.currentIndex])
                        .arg(startupSwitch.checked ? qsTr("开") : qsTr("关"))
                }

                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("恢复默认设置")
                    icon.name: "ic_fluent_arrow_reset_20_regular"
                    onClicked: confirmReset.ask(
                        qsTr("把外观、启动与系统开关恢复到默认值？启动台内容不会动。"),
                        function () {
                            ConfigManager.resetAppSettings()
                            oobe.model = ConfigManager.getSettings()
                            oobe.reloadControls()
                            oobe.step = 1
                        })
                }
            }

            Item { Layout.fillHeight: true }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.currentTheme.colors.dividerBorderColor
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 24
                spacing: 8

                Button {
                    text: qsTr("跳过引导")
                    visible: oobe.step < oobe.lastStep
                    onClicked: oobe.finish(true)
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: qsTr("上一步")
                    visible: oobe.step > 0
                    onClicked: oobe.step -= 1
                }

                Button {
                    text: oobe.step < oobe.lastStep ? qsTr("下一步") : qsTr("打开启动台")
                    highlighted: true
                    enabled: !oobe.saving
                    onClicked: {
                        if (oobe.step < oobe.lastStep) {
                            oobe.step += 1
                        } else {
                            oobe.finish(false)
                        }
                    }
                }
            }
        }
    }
}
