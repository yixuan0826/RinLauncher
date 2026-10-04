import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 快捷操作条目编辑器：名称 / 分区 / 图标 + 动作表单（ActionForm）。
//
// 「复制到启动台」会把一份内容拷到面板格子里，两边各管各的；这里维护的就是
// 被拷贝的模板本身。增删改走后端 add/updateAction。
AppDialog {
    id: dialog

    property var entry: ({})                 // 编辑中的原始条目；空对象 = 新增
    property string defaultCategory: ""      // 新增时的默认分区（当前选中的那个）

    // ── 表单状态 ──
    property string name: ""
    property string category: ""
    property string iconKey: ""
    property var categoryNames: []

    signal saved()

    title: dialog.entry && dialog.entry.id ? qsTr("编辑条目") : qsTr("新增条目")
    preferredWidth: 620
    preferredHeight: 620
    // 表单里有没保存的改动，点遮罩别把输入丢掉。
    closeOnScrim: false

    IconPickerDialog {
        id: iconPicker
        parent: dialog
        onPicked: dialog.iconKey = iconKey
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 10

        FormRow {
            label: qsTr("名称")
            TextField {
                id: nameField
                objectName: "recordNameField"
                Layout.fillWidth: true
                placeholderText: qsTr("例如：打开记事本")
                text: dialog.name
                onTextChanged: dialog.name = text
            }
        }

        FormRow {
            label: qsTr("分区")
            ComboBox {
                id: categoryCombo
                objectName: "recordCategoryCombo"
                Layout.preferredWidth: 220
                model: dialog.categoryNames
                onActivated: function (index) {
                    dialog.category = dialog.categoryNames[index] || dialog.category
                }
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
            ToolButton {
                icon.name: "ic_fluent_image_add_20_regular"
                ToolTip.text: qsTr("从文件获取图标（程序 / 快捷方式 / 图片）")
                onClicked: {
                    iconPicker.current = dialog.iconKey
                    iconPicker.openTab(3)
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

        ActionForm {
            id: actionForm
            objectName: "recordActionForm"
            Layout.fillWidth: true
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

    // ------------------------------------------------------------------
    // 打开与提交
    // ------------------------------------------------------------------
    function openFor(source, preferredCategory) {
        entry = source || ({})
        categoryNames = ConfigManager.getCategoriesModel()

        var target = ""
        if (entry && entry.category) {
            target = entry.category
        } else if (preferredCategory && preferredCategory.length > 0) {
            target = preferredCategory
        } else if (categoryNames.length > 0) {
            target = categoryNames[0]
        }
        category = target
        categoryCombo.currentIndex = Math.max(0, categoryNames.indexOf(category))

        name = entry && entry.name ? entry.name : ""
        iconKey = entry && entry.icon ? entry.icon : ""
        actionForm.load(entry || ({}))
        open()
    }

    function commit() {
        if (name.trim().length === 0) {
            ConfigManager.notify(qsTr("先给条目起个名字"), "warning")
            return
        }
        var invalid = actionForm.validate()
        if (invalid.length > 0) {
            ConfigManager.notify(invalid, "warning")
            return
        }

        var data = actionForm.read()
        // 从原条目克隆再覆盖：旧数据里可能还有 tooltip / hotkey 等字段，
        // 编辑一遍不应该把它们弄丢。
        var payload = entry && entry.id ? JSON.parse(JSON.stringify(entry)) : ({})
        payload.name = name.trim()
        payload.category = category || (categoryNames.length > 0 ? categoryNames[0] : "默认")
        payload.icon = iconKey
        payload.type = data.type
        payload.target = data.target
        payload.arguments = data.arguments
        payload.working_dir = data.working_dir
        payload.run_as = data.run_as
        payload.keyboard_steps = data.keyboard_steps
        if (payload.enabled === undefined) {
            payload.enabled = true
        }
        if (payload.order === undefined) {
            // 新条目排在本分区末尾：order 从当前条目总数起步就够用。
            payload.order = ConfigManager.getActions().length
        }

        var ok = payload.id
            ? ConfigManager.updateAction(payload)
            : ConfigManager.addAction(payload)
        if (!ok) {
            ConfigManager.notify(qsTr("保存失败，可以看看日志"), "error")
            return
        }
        saved()
        accept()
    }
}
