import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"
import "../dialogs"

// 启动台设置。
//
// 小窗现在有三块：一块最多 10 格的「双行面板」、一块存储/磁盘区，以及底部的
// 系统控制条（音量 / Wi-Fi / 热点）。面板上的每一格都是独立编辑的。
Item {
    id: launcherSettings

    readonly property int rowPanel: 0
    readonly property int rowStorage: 1
    // 容量以后端为准，别在两处各写一个 10。
    readonly property int panelCapacity: ConfigManager
        ? ConfigManager.getLauncherPanelUsage().capacity : 10

    // 两块的解析结果（含名称/图标/目标），小窗拿的是同一份数据。
    // 界面上显示的是「解析后」的列表（引用失效的槽位被后端跳过了），而编辑 /
    // 删除 / 移动都要用「原始列表」里的下标 —— 结果里的 rowIndex 就是那座桥。
    property var allSlots: []
    property var panelSlots: []
    property var storageSlots: []
    // 原始面板槽位数：超过 10 格时配置里还在，但小窗只显示前 10 格。
    property int panelSlotCount: 0
    property string storagePath: ""
    property var storage: ({})

    SlotEditorDialog {
        id: slotEditor
        objectName: "slotEditorDialog"
        onSaved: launcherSettings.reload()
    }

    StartMenuDialog {
        id: startMenuDialog
        objectName: "startMenuDialog"
        targetRow: launcherSettings.rowPanel
        onAccepted: launcherSettings.reload()
    }

    // ------------------------------------------------------------------
    // 界面
    // ------------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            spacing: 14

            Frame {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 46
                Layout.preferredHeight: 46
                radius: 12
                color: Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                               Theme.currentTheme.colors.primaryColor.g,
                               Theme.currentTheme.colors.primaryColor.b,
                               0.12)

                AppIcon {
                    anchors.centerIn: parent
                    iconKey: "ic_fluent_apps_20_regular"
                    iconSize: 24
                    tint: Utils.accentIconColor
                }
            }

            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 2

                Text {
                    font.bold: true
                    font.pixelSize: 22
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("启动台")
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: qsTr("从开始菜单添加")
                icon.name: "ic_fluent_add_20_regular"
                highlighted: true
                onClicked: startMenuDialog.open()
            }

            ToolButton {
                icon.name: "ic_fluent_arrow_sync_20_regular"
                ToolTip.text: qsTr("从磁盘重新加载配置")
                ToolTip.visible: hovered
                ToolTip.delay: 500
                onClicked: ConfigManager.reloadConfig()
            }
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: contentColumn.implicitHeight + 48
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: contentColumn
                x: Math.max(24, (scroller.width - width) / 2)
                width: Math.min(scroller.width - 48, 920)
                spacing: 18

                // ── 面板 ──
                SettingsGroup {
                    iconKey: "ic_fluent_dock_row_20_regular"
                    title: qsTr("应用面板")

                    // 配置里手动塞了超过 10 格时说明一声：小窗只会显示前 10 格。
                    Text {
                        Layout.fillWidth: true
                        visible: launcherSettings.panelSlotCount > launcherSettings.panelCapacity
                        wrapMode: Text.Wrap
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.systemCautionColor
                        text: qsTr("配置里有 %1 格，小窗只显示前 %2 格。")
                            .arg(launcherSettings.panelSlotCount)
                            .arg(launcherSettings.panelCapacity)
                    }

                    SlotListEditor {
                        objectName: "panelSlotList"
                        slots: launcherSettings.panelSlots
                        capacity: launcherSettings.panelCapacity
                        emptyHint: qsTr("面板还是空的，加一格就能在小窗上看到。")
                        unit: qsTr("格")
                        onAddRequested: slotEditor.openFor(launcherSettings.rowPanel, -1, null)
                        onEditRequested: launcherSettings.editSlot(launcherSettings.rowPanel, index)
                        onRemoveRequested: launcherSettings.removeSlot(launcherSettings.rowPanel, index)
                        onMoveRequested: launcherSettings.moveSlot(
                                             launcherSettings.rowPanel, index, delta)
                    }
                }

                // ── 存储与磁盘 ──
                SettingsGroup {
                    iconKey: "ic_fluent_hard_drive_20_regular"
                    title: qsTr("存储与磁盘")

                    FormRow {
                        label: qsTr("存储位置")
                        labelWidth: 88

                        TextField {
                            id: storageField
                            objectName: "storagePathField"
                            Layout.fillWidth: true
                            Layout.maximumWidth: 320
                            placeholderText: qsTr("留空 = 用户主目录")
                            text: launcherSettings.storagePath
                            // 敲完（回车或失焦）才落盘，不用每敲一个字写一次。
                            onEditingFinished: launcherSettings.setStoragePath(text)
                        }
                        Button {
                            text: qsTr("浏览…")
                            icon.name: "ic_fluent_folder_open_20_regular"
                            onClicked: {
                                var picked = ConfigManager.pickFolder()
                                if (picked.length > 0) {
                                    launcherSettings.setStoragePath(picked)
                                }
                            }
                        }
                        ToolButton {
                            icon.name: "ic_fluent_open_20_regular"
                            ToolTip.text: qsTr("打开这个目录")
                            onClicked: {
                                var current = storageField.text.length > 0
                                    ? storageField.text
                                    : launcherSettings.storage.path
                                ConfigManager.openPath(current)
                            }
                        }
                    }

                    SlotListEditor {
                        objectName: "storageSlotList"
                        slots: launcherSettings.storageSlots
                        emptyHint: qsTr("还没有磁盘入口。")
                        unit: qsTr("个入口")
                        onAddRequested: slotEditor.openFor(launcherSettings.rowStorage, -1, null)
                        onEditRequested: launcherSettings.editSlot(launcherSettings.rowStorage, index)
                        onRemoveRequested: launcherSettings.removeSlot(launcherSettings.rowStorage, index)
                        onMoveRequested: launcherSettings.moveSlot(
                                             launcherSettings.rowStorage, index, delta)
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        reload()
        applyPendingSlotEdit()
    }

    Connections {
        target: ConfigManager

        function onLauncherChanged() {
            launcherSettings.reload()
        }

        // 小窗里右键「编辑这一格…」会直接落到对应的编辑器上。
        function onSlotEditRequested(row, index) {
            launcherSettings.openSlotEditor(row, index)
        }
    }

    // ------------------------------------------------------------------
    // 数据
    // ------------------------------------------------------------------
    function reload() {
        // 一次取全，再按块分好 —— 比每块各调一次少几倍的解析。
        var slots = ConfigManager.getLauncherSlots()
        allSlots = slots
        panelSlots = filterRow(slots, rowPanel)
        storageSlots = filterRow(slots, rowStorage)
        panelSlotCount = filterRaw(rowPanel).length
        storagePath = ConfigManager.getLauncherStoragePath()
        storage = ConfigManager.getStorageInfo()
        syncStorageField()
    }

    function filterRow(slots, row) {
        return slots.filter(function (item) { return item.row === row })
    }

    // 输入框只在值真的变了时回填，免得把用户正在敲的内容顶掉。
    function syncStorageField() {
        if (storageField.text !== storagePath) {
            storageField.text = storagePath
        }
    }

    // ------------------------------------------------------------------
    // 交互
    // ------------------------------------------------------------------
    // 打开某一格的编辑器（index 是界面上解析后的序号）。
    function editSlot(row, index) {
        var shown = shownSlot(row, index)
        if (shown) {
            openSlotEditor(row, shown.rowIndex)
        }
    }

    // 按「原始列表」下标打开编辑器；index 为 -1 表示新增。
    function openSlotEditor(row, index) {
        if (index < 0) {
            slotEditor.openFor(row, -1, null)
            return
        }
        var raw = filterRaw(row)[index]
        if (raw) {
            slotEditor.openFor(row, index, raw)
        }
    }

    // 小窗右键「编辑这一格 / 再加一格」：页面可能刚切过来，把留下的请求取走。
    function applyPendingSlotEdit() {
        var pending = ConfigManager.takePendingSlotEdit()
        if (pending && pending.row !== undefined) {
            openSlotEditor(pending.row, pending.index)
        }
    }

    // 界面上第 index 个（解析后）对应的槽位；同时带着它在原始列表里的下标。
    function shownSlot(row, index) {
        var shown = filterRow(allSlots, row)
        return 0 <= index && index < shown.length ? shown[index] : null
    }

    function moveSlot(row, index, delta) {
        var shown = shownSlot(row, index)
        if (shown) {
            ConfigManager.moveLauncherSlot(row, shown.rowIndex, delta)
        }
    }

    function filterRaw(row) {
        return ConfigManager.getRawLauncherSlots().filter(function (item) {
            return item.row === row
        })
    }

    function removeSlot(row, index) {
        var shown = shownSlot(row, index)
        if (!shown) {
            return
        }
        var name = String(shown.label || shown.name || "")
        confirmRemove.message = name.length > 0
            ? qsTr("确定要移除「%1」这一格吗？").arg(name)
            : qsTr("确定要移除这一格吗？")
        confirmRemove.callback = function () {
            ConfigManager.deleteLauncherSlot(row, shown.rowIndex)
        }
        confirmRemove.open()
    }

    function setStoragePath(path) {
        path = String(path || "").trim()
        if (path === storagePath) {
            return
        }
        ConfigManager.setLauncherStoragePath(path)
    }

    ConfirmDialog {
        id: confirmRemove
        // 默认的 420px 在窄窗口下会被裁掉一截。
        width: 360
    }
}
