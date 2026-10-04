import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"
import "../dialogs"

// 快捷操作（动作模板库）。
//
// 左边分区、右边条目：条目和分区都在这里维护（新增 / 编辑 / 删除），
// 「复制到启动台」把一份内容拷到面板格子里，之后两边各管各的。
// 页面入口收在完整窗口标题栏右上角的「…」菜单里。
Item {
    id: recordsPage

    property var categories: []
    property var entries: []
    property string selectedCategory: ""
    property string query: ""

    ConfirmDialog {
        id: confirmDialog
    }

    RecordEntryDialog {
        id: entryDialog
        onSaved: recordsPage.reload()
    }

    CategoryEditorDialog {
        id: categoryDialog
        onSaved: recordsPage.reload()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── 顶部工具条 ──
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
                    text: qsTr("快捷操作")
                }
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("动作模板库：在这里维护，复制一份到启动台使用")
                }
            }

            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            Layout.bottomMargin: 16
            spacing: 16

            // ── 左：分区 ──
            Frame {
                Layout.preferredWidth: 300
                Layout.minimumWidth: 220
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 8
                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            font.bold: true
                            color: Theme.currentTheme.colors.textColor
                            text: qsTr("分区")
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("%1 个").arg(recordsPage.categories.length)
                        }
                        ToolButton {
                            Layout.alignment: Qt.AlignVCenter
                            objectName: "recordsAddCategoryButton"
                            icon.name: "ic_fluent_add_20_regular"
                            ToolTip.text: qsTr("新增分区")
                            onClicked: recordsPage.addCategory()
                        }
                    }

                    ListView {
                        id: categoryList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        model: recordsPage.categories

                        delegate: Frame {
                            id: categoryRow

                            width: categoryList.width
                            implicitHeight: 58
                            color: recordsPage.selectedCategory === modelData.name
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : Theme.currentTheme.colors.cardColor

                            // MouseArea 先声明、RowLayout 后声明：后声明的在上层，
                            // 行尾按钮才收得到点击；空白处的点击会落到 MouseArea。
                            MouseArea {
                                anchors.fill: parent
                                onClicked: recordsPage.selectCategory(modelData.name)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 6
                                spacing: 6

                                AppIcon {
                                    Layout.alignment: Qt.AlignVCenter
                                    iconKey: modelData.icon || ""
                                    iconSize: 20
                                    tint: Theme.currentTheme.colors.primaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0

                                    Text {
                                        Layout.fillWidth: true
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideRight
                                        color: Theme.currentTheme.colors.textColor
                                        text: modelData.name
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideRight
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: qsTr("%1 项").arg(modelData.entryCount)
                                    }
                                }

                                ToolButton {
                                    // 「默认」是所有落单条目的归宿，不让改也不让删。
                                    Layout.alignment: Qt.AlignVCenter
                                    visible: modelData.name !== "默认"
                                    icon.name: "ic_fluent_edit_20_regular"
                                    ToolTip.text: qsTr("重命名 / 换图标")
                                    onClicked: recordsPage.editCategory(modelData)
                                }
                                ToolButton {
                                    Layout.alignment: Qt.AlignVCenter
                                    visible: modelData.name !== "默认"
                                    icon.name: "ic_fluent_delete_20_regular"
                                    ToolTip.text: qsTr("删除分区（条目会移到默认）")
                                    onClicked: recordsPage.deleteCategory(modelData)
                                }
                            }
                        }
                    }
                }
            }

            // ── 右：条目 ──
            Frame {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    // 条目工具条。拆成两行：上一行是常驻的检索与全选，下一行只在
                    // 勾选了条目时冒出来 —— 一排挤七八个控件会把窄窗口撑爆。
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 8

                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            font.bold: true
                            color: Theme.currentTheme.colors.textColor
                            text: recordsPage.selectedCategory.length > 0
                                ? recordsPage.selectedCategory
                                : qsTr("全部操作")
                        }
                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("%1 项").arg(recordsPage.entries.length)
                        }

                        TextField {
                            Layout.fillWidth: true
                            Layout.maximumWidth: 240
                            placeholderText: qsTr("过滤操作…")
                            onTextChanged: recordsPage.query = text
                        }

                        Item { Layout.fillWidth: true }

                        Button {
                            Layout.alignment: Qt.AlignVCenter
                            text: qsTr("新增条目")
                            icon.name: "ic_fluent_add_20_regular"
                            onClicked: recordsPage.addEntry()
                        }
                    }

                    ListView {
                        id: entryList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 6
                        model: recordsPage.entries

                        delegate: Frame {
                            id: entryRow

                            width: entryList.width
                            implicitHeight: 64
                            color: Theme.currentTheme.colors.cardColor

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                spacing: 10

                                AppIcon {
                                    Layout.alignment: Qt.AlignVCenter
                                    iconKey: modelData.icon || ""
                                    iconSize: 24
                                    tint: modelData.enabled === false
                                        ? Theme.currentTheme.colors.textSecondaryColor
                                        : Theme.currentTheme.colors.primaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 80
                                    spacing: 2

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Text {
                                            Layout.fillWidth: true
                                            wrapMode: Text.NoWrap
                                            elide: Text.ElideRight
                                            color: Theme.currentTheme.colors.textColor
                                            text: modelData.name
                                        }
                                        // 停用的操作不会被执行，这里标出来免得找不着。
                                        Text {
                                            visible: modelData.enabled === false
                                            typography: Typography.Caption
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            text: qsTr("已停用")
                                        }
                                        Text {
                                            visible: modelData.run_as === "admin"
                                            typography: Typography.Caption
                                            color: Theme.currentTheme.colors.primaryColor
                                            text: qsTr("管理员")
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideMiddle
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: recordsPage.describe(modelData)
                                    }
                                }

                                RowLayout {
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 4

                                    MiniIconButton {
                                        iconName: "ic_fluent_dock_row_20_regular"
                                        tip: qsTr("复制到启动台")
                                        onClicked: recordsPage.copyToLauncher(modelData)
                                    }
                                    MiniIconButton {
                                        iconName: "ic_fluent_edit_20_regular"
                                        tip: qsTr("编辑")
                                        onClicked: recordsPage.editEntry(modelData)
                                    }
                                    MiniIconButton {
                                        iconName: "ic_fluent_delete_20_regular"
                                        tip: qsTr("删除")
                                        danger: true
                                        onClicked: recordsPage.deleteEntry(modelData)
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: recordsPage.entries.length === 0
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("还没有条目：点右上角「新增条目」开始。")
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // 数据
    // ------------------------------------------------------------------
    Component.onCompleted: reload()

    Connections {
        target: ConfigManager
        function onRecordsChanged() {
            recordsPage.reload()
        }
    }

    function reload() {
        // 每个分区带一个条目计数，免得列表里每行都去翻一遍完整条目表。
        var all = ConfigManager.getActions()
        var counts = {}
        for (var i = 0; i < all.length; ++i) {
            var name = all[i].category
            counts[name] = (counts[name] || 0) + 1
        }

        categories = ConfigManager.getCategories().sort(function (a, b) {
            return (a.order || 0) - (b.order || 0)
        }).map(function (item) {
            return {
                "id": item.id,
                "name": item.name,
                "icon": item.icon,
                "order": item.order,
                "expanded": item.expanded,
                "entryCount": counts[item.name] || 0
            }
        })

        if (selectedCategory.length > 0 && !categories.some(function (item) {
            return item.name === recordsPage.selectedCategory
        })) {
            // 选中的分区被删掉或改名了，退回到第一项。
            selectedCategory = categories.length > 0 ? categories[0].name : ""
        }
        refreshEntries()
    }

    function refreshEntries() {
        var needle = query.trim().toLowerCase()
        entries = ConfigManager.getActions().filter(function (item) {
            if (recordsPage.selectedCategory.length > 0
                    && item.category !== recordsPage.selectedCategory) {
                return false
            }
            if (needle.length === 0) {
                return true
            }
            // 名字与悬停提示都算命中，和检索框的直觉一致。
            return (item.name || "").toLowerCase().indexOf(needle) !== -1
                || (item.tooltip || "").toLowerCase().indexOf(needle) !== -1
        }).sort(function (a, b) {
            return (a.order || 0) - (b.order || 0)
        })
    }

    function describe(entry) {
        var kinds = {
            "file": qsTr("文件"),
            "cmd": qsTr("命令"),
            "url": qsTr("网址"),
            "keyboard": qsTr("按键")
        }
        var parts = [kinds[entry.type] || entry.type, entry.target || qsTr("(未设置)")]
        if (entry.hotkey) {
            parts.push(entry.hotkey)
        }
        return parts.join(" · ")
    }

    // ------------------------------------------------------------------
    // 交互
    // ------------------------------------------------------------------
    function selectCategory(name) {
        selectedCategory = name
        refreshEntries()
    }

    // 行尾按钮：拷一份到启动台面板（两边从此各管各的）。
    function copyToLauncher(entry) {
        ConfigManager.addActionToLauncher(entry.id, 0)
    }

    // ── 编辑（条目 + 分区都在这里维护）──
    function addEntry() {
        entryDialog.openFor(null, recordsPage.selectedCategory)
    }

    function editEntry(entry) {
        entryDialog.openFor(entry, recordsPage.selectedCategory)
    }

    function deleteEntry(entry) {
        confirmDialog.ask(qsTr("删除「%1」？引用了它的启动台格子会一起移除。").arg(entry.name),
                          function () { ConfigManager.deleteAction(entry.id) })
    }

    function addCategory() {
        categoryDialog.openFor(null)
    }

    function editCategory(category) {
        categoryDialog.openFor(category)
    }

    function deleteCategory(category) {
        confirmDialog.ask(qsTr("删除分区「%1」？里面的条目会移到「默认」。").arg(category.name),
                          function () { ConfigManager.deleteCategory(category.id) })
    }
}
