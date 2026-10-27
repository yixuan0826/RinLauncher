import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// Steam「添加非 Steam 游戏」风格的选择器：搜索 + 多选列表 + 底部添加。
// add 模式直接往启动台加槽位；pick 模式只把选中的应用交给条目编辑器回填。
AppDialog {
    id: dialog

    property var apps: []
    property var selected: ({})
    property int targetRow: 0
    property bool pickMode: false

    signal picked(var app)

    title: pickMode ? qsTr("选择一个开始菜单应用") : qsTr("从开始菜单添加")
    preferredWidth: 760
    preferredHeight: 680
    closeOnScrim: false

    readonly property int selectedCount: Object.keys(selected).length
    // 普通快捷方式 / UWP / WSA / WSL 合并成一张列表：都按名字排序，搜索框
    // 一视同仁；类型只作为右侧的小标签，不再用分页把用户切来切去。
    readonly property var visibleApps: apps.filter(function (app) {
        var query = searchField.text.trim().toLowerCase()
        if (query.length === 0) return true
        return (app.name + " " + app.target + " " + app.arguments + " "
                + (app.source || "")).toLowerCase().indexOf(query) >= 0
    })

    onAboutToShow: reload()

    function reload() {
        apps = ConfigManager.listStartMenuApps()
        selected = ({})
    }

    function keyOf(app) {
        return app.kind + "|" + app.target + "|" + app.arguments
    }

    function isSelected(app) {
        return selected[dialog.keyOf(app)] === true
    }

    function toggle(app) {
        var key = dialog.keyOf(app)
        var next = ({})
        for (var existing in selected) {
            if (existing !== key) next[existing] = true
        }
        if (selected[key] !== true) next[key] = true
        selected = next
    }

    function kindIcon(kind) {
        if (kind === "uwp") return "ic_fluent_window_20_regular"
        if (kind === "wsa") return "ic_fluent_phone_20_regular"
        if (kind === "wsl") return "ic_fluent_code_20_regular"
        return "ic_fluent_apps_20_regular"
    }

    function kindLabel(kind) {
        if (kind === "uwp") return qsTr("UWP")
        if (kind === "wsa") return qsTr("WSA")
        if (kind === "wsl") return qsTr("WSL")
        return qsTr("快捷方式")
    }

    function detailOf(app) {
        if (app.kind === "uwp") return app.target
        if (app.kind === "wsl") return app.arguments
        // WSA 的 target 是 WsaClient.exe，对用户没意义；显示快捷方式自己的路径。
        if (app.kind === "wsa") return app.source || app.target
        return app.target + (app.arguments.length > 0 ? " " + app.arguments : "")
    }

    function chosenApps() {
        return apps.filter(function (app) { return dialog.isSelected(app) })
    }

    function commit() {
        var chosen = chosenApps()
        if (chosen.length === 0) {
            ConfigManager.notify(qsTr("先选一个应用"), "warning")
            return
        }
        if (pickMode) {
            picked(chosen[0])
            accept()
            return
        }
        var added = 0
        for (var index = 0; index < chosen.length; ++index) {
            if (ConfigManager.addAppSlot(chosen[index], targetRow)) added += 1
        }
        if (added > 0) {
            ConfigManager.notify(qsTr("已添加 %1 个应用").arg(added), "success")
            accept()
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: qsTr("搜索应用…")
            }
            Button {
                text: qsTr("浏览 .lnk…")
                icon.name: "ic_fluent_folder_open_20_regular"
                onClicked: {
                    var path = ConfigManager.pickShortcut()
                    if (!path) return
                    var app = ConfigManager.parseShortcut(path)
                    if (!app.target) {
                        ConfigManager.notify(qsTr("这个快捷方式没有可启动的目标"), "warning")
                        return
                    }
                    dialog.apps = [app].concat(dialog.apps)
                    dialog.toggle(app)
                }
            }
            ToolButton {
                icon.name: "ic_fluent_arrow_sync_20_regular"
                ToolTip.text: qsTr("重新扫描")
                onClicked: dialog.reload()
            }
        }

        Frame {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: appList
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                spacing: 2
                model: dialog.visibleApps
                ScrollBar.vertical: ScrollBar {}

                delegate: Rectangle {
                    id: row

                    readonly property var app: modelData
                    readonly property bool checked: dialog.isSelected(app)

                    width: appList.width
                    height: 56
                    radius: Theme.currentTheme.appearance.windowRadius
                    color: checked
                        ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                                  Theme.currentTheme.colors.primaryColor.g,
                                  Theme.currentTheme.colors.primaryColor.b, 0.14)
                        : (rowMouse.containsMouse
                           ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent")

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dialog.toggle(row.app)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 12

                        CheckBox {
                            checked: row.checked
                            onClicked: dialog.toggle(row.app)
                        }

                        AppIcon {
                            Layout.preferredWidth: 24
                            Layout.preferredHeight: 24
                            iconKey: row.app.icon.length > 0
                                ? row.app.icon : dialog.kindIcon(row.app.kind)
                            iconSize: 24
                            tint: Theme.currentTheme.colors.textColor
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 2

                            Text {
                                Layout.fillWidth: true
                                // 名称只占一行：高度用 RinUI 的 Body 行高，长名字统一走省略号，
                                // 不会把下面一行挤歪、也不会把行距撑成参差不齐。
                                Layout.preferredHeight: Theme.currentTheme.typography.bodyLineHeight
                                wrapMode: Text.NoWrap
                                maximumLineCount: 1
                                elide: Text.ElideRight
                                color: Theme.currentTheme.colors.textColor
                                text: row.app.name
                            }
                            Text {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.currentTheme.typography.captionLineHeight
                                wrapMode: Text.NoWrap
                                maximumLineCount: 1
                                elide: Text.ElideMiddle
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: dialog.detailOf(row.app)
                            }
                        }

                        // 类型标签：Fluent 的浅底小胶囊，比裸文字更好认，也不抢名称的宽度。
                        Rectangle {
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredWidth: kindText.implicitWidth + 14
                            Layout.preferredHeight: 20
                            radius: Theme.currentTheme.appearance.smallRadius
                            color: Theme.currentTheme.colors.subtleSecondaryColor

                            Text {
                                id: kindText
                                anchors.centerIn: parent
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: dialog.kindLabel(row.app.kind)
                            }
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: appList.count === 0
                width: parent.width - 32
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("没有找到应用。换个关键词，或手动选择 .lnk。")
            }
        }
    }

    footer: RowLayout {
        spacing: 8

        Text {
            Layout.alignment: Qt.AlignVCenter
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("已选 %1 项").arg(dialog.selectedCount)
        }

        Item { Layout.fillWidth: true }

        Button {
            text: qsTr("先别……")
            onClicked: dialog.reject()
        }

        Button {
            text: dialog.pickMode ? qsTr("使用这个应用") : qsTr("添加所选")
            highlighted: true
            enabled: dialog.selectedCount > 0
            onClicked: dialog.commit()
        }
    }
}
