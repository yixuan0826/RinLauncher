import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 分区编辑器：名称 + 图标。删除分区的动作在页面上（带确认），
// 删掉后里面的条目会落回「默认」（后端处理）。
AppDialog {
    id: dialog

    property var category: ({})
    property string name: ""
    property string iconKey: ""

    signal saved()

    title: dialog.category && dialog.category.id ? qsTr("编辑分区") : qsTr("新增分区")
    preferredWidth: 460
    closeOnScrim: false

    IconPickerDialog {
        id: iconPicker
        parent: dialog
        onPicked: dialog.iconKey = iconKey
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 10

        FormRow {
            label: qsTr("名称")
            TextField {
                id: nameField
                objectName: "categoryNameField"
                Layout.fillWidth: true
                placeholderText: qsTr("例如：常用")
                text: dialog.name
                onTextChanged: dialog.name = text
            }
        }

        FormRow {
            label: qsTr("图标")
            ToolButton {
                icon.name: "ic_fluent_icons_20_regular"
                ToolTip.text: qsTr("从图标库中选择")
                onClicked: {
                    iconPicker.current = dialog.iconKey
                    iconPicker.open()
                }
            }
            AppIcon {
                Layout.alignment: Qt.AlignVCenter
                iconKey: dialog.iconKey
                iconSize: 22
                placeholder: "ic_fluent_dismiss_20_regular"
            }
            ToolButton {
                icon.name: "ic_fluent_delete_20_regular"
                ToolTip.text: qsTr("清除图标")
                enabled: dialog.iconKey.length > 0
                onClicked: dialog.iconKey = ""
            }
        }
    }

    footer: RowLayout {
        spacing: 8

        Item { Layout.fillWidth: true }

        Button {
            text: qsTr("取消")
            onClicked: dialog.reject()
        }

        Button {
            text: qsTr("保存")
            highlighted: true
            onClicked: dialog.commit()
        }
    }

    function openFor(source) {
        category = source || ({})
        name = category.name || ""
        iconKey = category.icon || ""
        open()
    }

    function commit() {
        var trimmed = name.trim()
        if (trimmed.length === 0) {
            ConfigManager.notify(qsTr("分区需要一个名字"), "warning")
            return
        }
        // 重名检查：编辑时改没改名都放行（后端按 id 更新），新增时不许撞名。
        var existing = ConfigManager.getCategoriesModel()
        var renamed = !category || !category.id || category.name !== trimmed
        if (renamed && existing.indexOf(trimmed) >= 0) {
            ConfigManager.notify(qsTr("已经有同名的分区了"), "warning")
            return
        }

        if (category && category.id) {
            var payload = JSON.parse(JSON.stringify(category))
            payload.name = trimmed
            payload.icon = iconKey
            if (!ConfigManager.updateCategory(payload)) {
                ConfigManager.notify(qsTr("保存失败，可以看看日志"), "error")
                return
            }
        } else {
            var maxOrder = 0
            var categories = ConfigManager.getCategories()
            for (var i = 0; i < categories.length; ++i) {
                var order = categories[i].order || 0
                // 「默认」挂着 99 的哨兵排序，新分区排到它前面。
                if (order < 99 && order > maxOrder) {
                    maxOrder = order
                }
            }
            if (!ConfigManager.addCategory({
                "name": trimmed,
                "icon": iconKey,
                "order": maxOrder + 1,
                "expanded": true
            })) {
                ConfigManager.notify(qsTr("保存失败，可以看看日志"), "error")
                return
            }
        }
        saved()
        accept()
    }
}
