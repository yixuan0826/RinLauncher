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
    readonly property var visibleApps: apps.filter(function (app) {
        var tab = tabs.currentIndex
        if (tab === 0 && app.kind !== "lnk") return false
        if (tab === 1 && app.kind !== "uwp") return false
        if (tab === 2 && app.kind !== "wsl") return false
        var query = searchField.text.trim().toLowerCase()
        if (query.length === 0) return true
        return (app.name + " " + app.target + " " + app.arguments)
            .toLowerCase().indexOf(query) >= 0
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
        if (kind === "wsl") return "ic_fluent_code_20_regular"
        return "ic_fluent_apps_20_regular"
    }

    function kindLabel(kind) {
        if (kind === "uwp") return qsTr("UWP / WSA")
        if (kind === "wsl") return qsTr("WSL")
        return qsTr("快捷方式")
    }

    function detailOf(app) {
        if (app.kind === "uwp") return app.target
        if (app.kind === "wsl") return app.arguments
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

        Segmented {
            id: tabs
            Layout.alignment: Qt.AlignLeft
            SegmentedItem { text: qsTr("开始菜单") }
            SegmentedItem { text: qsTr("UWP / WSA") }
            SegmentedItem { text: qsTr("WSL") }
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
                    height: 54
                    radius: 6
                    color: checked
                        ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                                  Theme.currentTheme.colors.primaryColor.g,
                                  Theme.currentTheme.colors.primaryColor.b, 0.14)
                        : (rowMouse.containsMouse
                           ? Theme.currentTheme.colors.controlSecondaryColor : "transparent")

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: dialog.toggle(row.app)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 12
                        spacing: 10

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
                            tint: Utils.accentIconColor
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 0

                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                color: Theme.currentTheme.colors.textColor
                                text: row.app.name
                            }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.NoWrap
                                elide: Text.ElideMiddle
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: dialog.detailOf(row.app)
                            }
                        }

                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: dialog.kindLabel(row.app.kind)
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
                text: qsTr("没有找到应用。可以换个分页，或手动选择 .lnk。")
            }
        }

        Text {
            Layout.fillWidth: true
            visible: tabs.currentIndex === 2
            wrapMode: Text.Wrap
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("WSL 条目会打开对应发行版的默认 shell，保存后可在编辑里补充命令。")
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
            text: qsTr("取消")
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
