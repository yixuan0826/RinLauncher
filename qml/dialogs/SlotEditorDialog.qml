import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 启动台格子编辑器：加一格 / 改一格。
//
// 槽位有四种，表单里只显示与当前类型相关的那几行 —— 与其把所有字段都摆出来再
// 灰掉，不如按类型换表单，少一层判断也少一处看走眼的机会。整个表单可滚动：
// 按键序列这种越加越长的字段不会再把 footer 挤出卡片。
// 动作类槽位自带完整定义：类型 / 目标 / 参数 / 工作目录 / 管理员 / 按键序列
// 全写在这一格里，不依赖任何外部条目库。
AppDialog {
    id: editor

    property int row: 0
    property int index: -1          // -1 表示新增
    property var slot: ({})

    // ── 表单状态 ──
    property string kind: "action"
    property string toolKey: ""
    property string path: ""
    property string label: ""
    property string iconKey: ""

    // 下拉的模型与后端取值
    property var toolNames: []
    property var toolKeys: []
    property var drives: []

    signal saved()

    title: index < 0 ? qsTr("添加一格") : qsTr("编辑这一格")
    preferredWidth: 620
    preferredHeight: 600
    // 表单里有没保存的改动，点遮罩别把输入丢掉。
    closeOnScrim: false

    // parent 显式指到弹窗根上：默认内容会被 body 那个 Layout 接管，嵌套弹窗
    // 要铺满整页就不能待在布局里。
    IconPickerDialog {
        id: iconPicker
        parent: editor
        onPicked: editor.iconKey = iconKey
    }

    StartMenuDialog {
        id: startMenuPicker
        objectName: "startMenuPicker"
        parent: editor
        pickMode: true
        onPicked: {
            editor.kind = "action"
            editor.label = app.name || ""
            editor.iconKey = app.icon || ""
            inlineAction.load({
                "type": app.kind === "uwp" ? "uwp"
                        : (app.kind === "wsl" ? "cmd" : "file"),
                "target": app.target || "",
                "arguments": app.arguments || "",
                "working_dir": app.working_dir || "",
                "run_as": "user",
                "keyboard_steps": []
            })
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 10

        // 表单放进 Flickable：字段多（尤其是按键序列）时内容会比卡片高，
        // 没有滚动的话底部几行和 footer 会被挤出卡片外面。
        Flickable {
            id: formScroller
            objectName: "slotFormScroller"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: formColumn.implicitHeight + 6
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: formColumn
                width: formScroller.width
                spacing: 12

        Button {
            Layout.fillWidth: true
            highlighted: true
            text: qsTr("从开始菜单导入…")
            icon.name: "ic_fluent_apps_20_regular"
            onClicked: startMenuPicker.open()
        }

        // ── 预览 ──
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 92

            RowLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 14

                AppIcon {
                    Layout.alignment: Qt.AlignVCenter
                    iconKey: editor.iconKey.length > 0 ? editor.iconKey : editor.previewIcon
                    iconSize: 40
                    tint: Utils.accentIconColor
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.NoWrap
                        elide: Text.ElideRight
                        font.bold: true
                        color: Theme.currentTheme.colors.textColor
                        text: editor.previewName
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.NoWrap
                        elide: Text.ElideMiddle
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: editor.previewDetail
                    }
                }
            }
        }

        // ── 类型：四张可选卡片，比下拉框更直观 ──
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                font.bold: true
                font.pixelSize: Theme.currentTheme.typography.bodySize + 1
                color: Theme.currentTheme.colors.textColor
                text: qsTr("这一格用来做什么？")
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: editor.kindHint
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: editor.kindOptions

                delegate: Frame {
                    id: kindTile

                    readonly property bool selected: editor.kind === modelData.kind

                    Layout.fillWidth: true
                    Layout.preferredHeight: 58
                    radius: 8
                    color: selected
                        ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                                  Theme.currentTheme.colors.primaryColor.g,
                                  Theme.currentTheme.colors.primaryColor.b, 0.16)
                        : (kindMouse.containsMouse
                            ? Theme.currentTheme.colors.controlSecondaryColor
                            : Theme.currentTheme.colors.cardColor)

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 8
                        spacing: 8

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: modelData.icon
                            iconSize: 18
                            tint: kindTile.selected
                                ? Utils.accentIconColor
                                : Theme.currentTheme.colors.textColor
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            font.pixelSize: Theme.currentTheme.typography.bodySize - 1
                            font.bold: kindTile.selected
                            color: kindTile.selected
                                ? Theme.currentTheme.colors.primaryColor
                                : Theme.currentTheme.colors.textColor
                            text: modelData.title
                        }
                    }

                    MouseArea {
                        id: kindMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: editor.kind = modelData.kind
                    }

                    ToolTip.text: modelData.hint
                    ToolTip.visible: kindMouse.containsMouse
                    ToolTip.delay: 500
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // ── 动作字段：这一格自带完整定义 ──
        ActionForm {
            id: inlineAction
            objectName: "slotActionForm"
            visible: editor.kind === "action"
        }

        // ── 内置功能 ──
        FormRow {
            visible: editor.kind === "tool"
            label: qsTr("功能")
            description: qsTr("小窗自带的功能")
            ComboBox {
                Layout.fillWidth: true
                Layout.maximumWidth: 320
                model: editor.toolNames
                currentIndex: Math.max(0, editor.toolKeys.indexOf(editor.toolKey))
                onActivated: function (index) {
                    editor.toolKey = editor.toolKeys[index] || ""
                }
            }
        }

        // ── 文件 / 文件夹 / 磁盘 ──
        FormRow {
            visible: editor.kind === "path"
            label: qsTr("路径")
            description: qsTr("点开就打开这个位置")
            TextField {
                Layout.fillWidth: true
                placeholderText: qsTr("例如 D:\\ 或 C:\\Tools")
                text: editor.path
                onTextChanged: editor.path = text
            }
            ToolButton {
                icon.name: "ic_fluent_folder_open_20_regular"
                ToolTip.text: qsTr("选一个文件夹")
                onClicked: {
                    var picked = ConfigManager.pickFolder()
                    if (picked.length > 0) {
                        editor.path = picked
                    }
                }
            }
            ToolButton {
                icon.name: "ic_fluent_document_20_regular"
                ToolTip.text: qsTr("选一个文件")
                onClicked: {
                    var picked = ConfigManager.pickFile()
                    if (picked.length > 0) {
                        editor.path = picked
                    }
                }
            }
        }

        FormRow {
            visible: editor.kind === "path" && editor.drives.length > 0
            label: qsTr("磁盘")
            description: qsTr("一键把路径填成某个盘")
            ComboBox {
                Layout.fillWidth: true
                Layout.maximumWidth: 320
                model: editor.driveLabels
                onActivated: function (index) {
                    editor.path = editor.drives[index].path
                }
            }
        }

        FormRow {
            visible: editor.kind === "usb"
            label: qsTr("可移动磁盘")
            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("插上后自动识别第一个可移动磁盘。")
            }
        }

        FormRow {
            label: qsTr("显示名")
            description: qsTr("留空就用目标自己的名字")
            TextField {
                Layout.fillWidth: true
                Layout.maximumWidth: 320
                placeholderText: qsTr("（可选）")
                text: editor.label
                onTextChanged: editor.label = text
            }
        }

        FormRow {
            label: qsTr("图标")
            description: qsTr("留空就用目标自己的图标")
            ToolButton {
                icon.name: "ic_fluent_icons_20_regular"
                ToolTip.text: qsTr("从图标库中选择")
                onClicked: {
                    iconPicker.current = editor.iconKey
                    iconPicker.open()
                }
            }
            ToolButton {
                icon.name: "ic_fluent_image_add_20_regular"
                ToolTip.text: qsTr("从文件获取图标（程序 / 快捷方式 / 图片）")
                onClicked: {
                    iconPicker.current = editor.iconKey
                    iconPicker.openTab(3)
                }
            }
            AppIcon {
                Layout.alignment: Qt.AlignVCenter
                iconKey: editor.iconKey
                iconSize: 22
                placeholder: "ic_fluent_dismiss_20_regular"
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.NoWrap
                elide: Text.ElideMiddle
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: editor.iconKey
            }
            ToolButton {
                icon.name: "ic_fluent_delete_20_regular"
                ToolTip.text: qsTr("清除图标")
                enabled: editor.iconKey.length > 0
                onClicked: editor.iconKey = ""
            }
        }
            }
        }
    }

    footer: RowLayout {
        spacing: 8

        Text {
            Layout.alignment: Qt.AlignVCenter
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("保存后立即生效")
        }

        Item { Layout.fillWidth: true }

        Button {
            text: qsTr("取消")
            onClicked: editor.reject()
        }

        Button {
            text: qsTr("保存")
            highlighted: true
            onClicked: editor.commit()
        }
    }

    // ------------------------------------------------------------------
    // 取值
    // ------------------------------------------------------------------
    readonly property var kindOptions: [
        {"kind": "action", "title": qsTr("动作"), "icon": "ic_fluent_play_20_regular",
         "hint": qsTr("程序、命令、网址或按键")},
        {"kind": "tool", "title": qsTr("内置功能"), "icon": "ic_fluent_wrench_20_regular",
         "hint": qsTr("设置、重载、隐藏等内置功能")},
        {"kind": "path", "title": qsTr("打开路径"), "icon": "ic_fluent_folder_open_20_regular",
         "hint": qsTr("文件、文件夹或磁盘")},
        {"kind": "usb", "title": qsTr("可移动磁盘"), "icon": "ic_fluent_usb_plug_20_regular",
         "hint": qsTr("自动识别移动磁盘")}
    ]

    readonly property string kindTitle: {
        for (var i = 0; i < kindOptions.length; ++i) {
            if (kindOptions[i].kind === kind) {
                return kindOptions[i].title
            }
        }
        return ""
    }

    readonly property string kindHint: {
        for (var i = 0; i < kindOptions.length; ++i) {
            if (kindOptions[i].kind === kind) {
                return kindOptions[i].hint
            }
        }
        return ""
    }

    readonly property var driveLabels: drives.map(function (item) {
        return item.total.length > 0
            ? "%1（%2，剩余 %3）".arg(item.label).arg(item.kindLabel).arg(item.free)
            : "%1（%2）".arg(item.label).arg(item.kindLabel)
    })

    readonly property string previewName: {
        if (label.length > 0) {
            return label
        }
        if (kind === "action") {
            return editor.deriveActionName()
        }
        if (kind === "tool") {
            var ti = toolKeys.indexOf(toolKey)
            return ti >= 0 ? toolNames[ti] : qsTr("未选择功能")
        }
        if (kind === "usb") {
            return qsTr("可移动磁盘")
        }
        return path.length > 0 ? path : qsTr("未设置路径")
    }

    // 内联动作没有名字：按类型从目标里取一个一眼能懂的显示名（与后端一致）。
    function deriveActionName() {
        var data = inlineAction.read()
        if (data.type === "keyboard") {
            return qsTr("按键动作")
        }
        if (data.type === "uwp") {
            return qsTr("UWP 应用")
        }
        if (data.target.length === 0) {
            return qsTr("未配置动作")
        }
        if (data.type === "url") {
            return data.target
        }
        var parts = data.target.replace(/\\/g, "/").split("/")
        return parts[parts.length - 1] || data.target
    }

    readonly property string previewDetail: {
        if (kind === "action") {
            return qsTr("%1 · 由这一格自己定义").arg(kindTitle)
        }
        if (kind === "tool") {
            return qsTr("%1 · 小窗自带").arg(kindTitle)
        }
        if (kind === "usb") {
            return qsTr("%1 · 插上后自动识别").arg(kindTitle)
        }
        return qsTr("%1 · %2").arg(kindTitle).arg(path.length > 0 ? path : qsTr("未设置路径"))
    }

    readonly property string previewIcon: {
        if (kind === "action") {
            return "ic_fluent_play_20_regular"
        }
        if (kind === "tool") {
            return "ic_fluent_wrench_20_regular"
        }
        if (kind === "usb") {
            return "ic_fluent_usb_plug_20_regular"
        }
        return "ic_fluent_folder_open_20_regular"
    }

    // ------------------------------------------------------------------
    // 打开与提交
    // ------------------------------------------------------------------
    function openFor(targetRow, targetIndex, existing) {
        row = targetRow
        index = targetIndex
        slot = existing || {}

        kind = slot.kind || "action"
        toolKey = slot.key || ""
        path = slot.path || ""
        label = slot.label || ""
        iconKey = slot.icon || ""

        // 动作就是这一格自己的定义。
        inlineAction.load(slot.action || {})

        var tools = ConfigManager.getToolCatalog()
        toolNames = tools.map(function (item) { return item.title })
        toolKeys = tools.map(function (item) { return item.key })

        drives = ConfigManager.getDrives()
        open()
    }

    function commit() {
        // 新增面板格子先查一下还剩几格：满了直接拦住，不去惊动后端写盘。
        if (index < 0 && row === 0) {
            var usage = ConfigManager.getLauncherPanelUsage()
            if (usage.used >= usage.capacity) {
                ConfigManager.notify(qsTr("面板最多 %1 格，先删一格再加。").arg(usage.capacity),
                                     "warning")
                return
            }
        }
        if (kind === "action") {
            var invalid = inlineAction.validate()
            if (invalid.length > 0) {
                ConfigManager.notify(invalid, "warning")
                return
            }
        } else if (kind === "tool" && toolKey.length === 0) {
            ConfigManager.notify(qsTr("请先选一个内置功能"), "warning")
            return
        }
        if (kind === "path" && path.trim().length === 0) {
            ConfigManager.notify(qsTr("请先填一个路径"), "warning")
            return
        }

        // 动作一律写成内联：这一格自己带着完整定义。
        var payload = {
            "kind": kind,
            "label": label.trim(),
            "icon": iconKey,
            "key": kind === "tool" ? toolKey : "",
            "path": kind === "path" ? path.trim() : "",
            "action": kind === "action" ? inlineAction.read() : null
        }
        var ok = index < 0
            ? ConfigManager.addLauncherSlot(row, payload)
            : ConfigManager.updateLauncherSlot(row, index, payload)
        if (!ok) {
            ConfigManager.notify(qsTr("保存失败：内容不完整或面板已满，可以看看日志"), "error")
            return
        }
        saved()
        accept()
    }
}
