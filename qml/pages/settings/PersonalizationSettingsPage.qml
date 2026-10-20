import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../../components"

// 设置 → 个性化：主题模式、强调色（可提取系统色）、窗口材质、动画。
Item {
    id: pageRoot

    property var page

    // 颜色选择器在组件构造阶段会从默认红色发出一次 colorChanged。
    // 只有「已完成回填」且「用户真正打开过选择器」时才把它当成用户操作。
    property bool accentReady: false
    property bool accentUserEditing: false

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
                title: qsTr("主题")
                iconKey: "ic_fluent_paint_brush_20_regular"

                FormRow {
                    label: qsTr("主题模式")
                    ComboBox {
                        id: themeCombo
                        Layout.preferredWidth: 180
                        model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]
                        onActivated: function (index) {
                            pageRoot.page.apply("theme",
                                ["system", "light", "dark"][index])
                        }
                    }
                }

                FormRow {
                    label: qsTr("跟随系统强调色")
                    Switch {
                        id: followAccentSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("accentColorMode",
                                checked ? "system" : "custom")
                            if (!checked) {
                                // 取消跟随时把当前系统色存成自定义色，颜色不跳变。
                                pageRoot.page.apply("accentColor", ConfigManager.accentColor)
                            }
                        }
                    }
                }

                FormRow {
                    label: qsTr("强调色")
                    RowLayout {
                        spacing: 8

                        DropDownColorPicker {
                            id: accentPicker
                            Layout.preferredWidth: 150
                            enabled: !followAccentSwitch.checked
                            onClicked: pageRoot.accentUserEditing = true
                            onColorChanged: {
                                if (!pageRoot.accentReady || !pageRoot.accentUserEditing) return
                                if (!pageRoot.page || pageRoot.page.syncing) return
                                pageRoot.page.apply("accentColor", color.toString())
                                pageRoot.page.apply("accentColorMode", "custom")
                            }
                        }

                        Button {
                            text: qsTr("从系统提取")
                            icon.name: "ic_fluent_color_20_regular"
                            onClicked: pageRoot.pickSystemAccent()
                        }

                        ToolButton {
                            icon.name: "ic_fluent_arrow_reset_20_regular"
                            ToolTip.text: qsTr("恢复默认强调色")
                            onClicked: pageRoot.applyAccent("#0078d4")
                        }
                    }
                }

                FormRow {
                    label: qsTr("窗口材质")
                    description: qsTr("云母需要 Windows 11")
                    ComboBox {
                        id: materialCombo
                        Layout.preferredWidth: 180
                        model: [qsTr("增强云母"), qsTr("云母"), qsTr("不透明")]
                        onActivated: function (index) {
                            pageRoot.page.apply("material",
                                ["tabbed", "mica", "none"][index])
                        }
                    }
                }

                FormRow {
                    label: qsTr("动画效果")
                    Switch {
                        id: animationSwitch
                        checkedText: qsTr("开")
                        uncheckedText: qsTr("关")
                        onCheckedChanged: {
                            if (!pageRoot.page || pageRoot.page.syncing) return
                            pageRoot.page.apply("animationEnabled", checked)
                        }
                    }
                }
            }
        }
    }

    function applyAccent(value) {
        pageRoot.accentReady = false
        pageRoot.accentUserEditing = false
        accentPicker.color = value
        pageRoot.accentReady = true
        if (pageRoot.page) {
            pageRoot.page.apply("accentColorMode", "custom")
            pageRoot.page.apply("accentColor", value)
        }
    }

    function pickSystemAccent() {
        var value = ConfigManager.systemAccentColor()
        if (!value) {
            ConfigManager.notify(qsTr("没能读到系统主题色，请手动选择"), "warning")
            return
        }
        applyAccent(value)
        ConfigManager.notify(qsTr("已从系统提取强调色 %1").arg(value.toUpperCase()), "success")
    }

    function reload() {
        var model = page.model
        pageRoot.accentReady = false
        pageRoot.accentUserEditing = false
        themeCombo.currentIndex = Math.max(0,
            ["system", "light", "dark"].indexOf(model.theme))
        followAccentSwitch.checked = (model.accentColorMode || "custom") === "system"
        accentPicker.color = model.accentColor || "#0078d4"
        materialCombo.currentIndex = Math.max(0,
            ["tabbed", "mica", "none"].indexOf(model.material || "tabbed"))
        animationSwitch.checked = model.animationEnabled !== false
        Qt.callLater(function () { pageRoot.accentReady = true })
    }
}
