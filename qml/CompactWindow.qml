import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI
// QtQuick.Window 必须排在 RinUI 后面：QML 里后导入的类型优先级更高，否则 Window
// 会解析到 RinUI 那套自带标题栏与背景矩形的窗口包装，桌面挂件就变成普通窗口了。
// 副作用是 QtQuick 的 Text 也会盖过 RinUI 的 Text，所以本文件里的文字用
// font.pixelSize / color 这些 Qt 原生属性，不写 RinUI 特有的 typography。
import QtQuick.Window 2.15

import "components"

// 常驻桌面右下角的启动台小窗。
//
// 两块内容（都在完整窗口的「启动台」页里配）：
//   面板：最多 10 格的双行格子板（≤ 5 格一排，更多时平分两排）
//   存储区：存储卡片 + 磁盘入口
// 窗口是「沉底」的桌面挂件：无边框、不抢焦点、不进任务栏，也不盖在别的窗口
// 之上 —— 它贴在主显示器右下角，被普通窗口盖住，像桌面上的一块部件。
// 高度固定为桌面可用高度的一半（见 rin_launcher/effects.py）。
Window {
    id: compact

    // ── 形态 ──
    // 窗口与卡片同尺寸：亚克力与系统圆角直接作用在窗口上，外面不套透明边，
    // 也就没有那一圈「玻璃边框」。投影交给系统，QML 不再自绘。
    readonly property int edgeMargin: 16      // 贴边时与桌面边缘的距离
    readonly property int contentMargin: 14   // 卡片内的内容留白
    readonly property int cardRadius: 8       // 与 DWM 的窗口圆角保持一致

    width: 400
    height: Math.max(400, Math.round(Screen.desktopAvailableHeight / 2))
    visible: false
    color: "transparent"
    title: qsTr("启动台")
    // 无边框 + 工具窗口（不占任务栏）+ 不接受焦点 + 全局置底。置底由这里声明，
    // Python 侧显示时再用 SetWindowPos(HWND_BOTTOM) 兜一次底
    // （见 effects.apply_bottom_layer）。
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnBottomHint

    // 亚克力是否真的上成功了（Windows 11 / 10 才有）。后端会 setProperty 进来：
    // 没上成功就把卡片画得实一点，免得在透明背景上看着发虚。
    property bool acrylicActive: false

    // ── 状态 ──
    property var panelSlots: []
    property var storageSlots: []
    property var storage: ({})

    // 小窗只发信号，窗口切换 / 退出这类跨窗口的活儿统一交给 Python 决定。
    signal openMainRequested(string page)
    signal hideRequested()
    signal quitRequested()

    // ------------------------------------------------------------------
    // 位置：固定贴主显示器右下角，不拖动、不记忆。
    // ------------------------------------------------------------------
    function snapToCorner() {
        // Screen 给的是窗口所在（未显示时是主）显示器的可用区域，已经排除任务栏。
        x = Screen.virtualX + Screen.desktopAvailableWidth - width - edgeMargin
        y = Screen.virtualY + Screen.desktopAvailableHeight - height - edgeMargin
    }

    // 显示时贴回右下角；分辨率 / 任务栏变化时窗口高度会跟着变，顺带重贴一次。
    onVisibleChanged: {
        if (visible) {
            snapToCorner()
        }
    }
    onHeightChanged: snapToCorner()

    // ------------------------------------------------------------------
    // 动画总开关：设置里关掉后把 RinUI 的全局动画时长清成 0。
    // ------------------------------------------------------------------
    property var _animDefaults: null

    function applyAnimationSetting() {
        if (compact._animDefaults === null) {
            // 第一次把 RinUI 的默认值抄下来，之后在默认值和 0 之间来回切。
            compact._animDefaults = {
                "animationSpeed": Utils.animationSpeed,
                "animationSpeedExpander": Utils.animationSpeedExpander,
                "animationSpeedFaster": Utils.animationSpeedFaster,
                "appearanceSpeed": Utils.appearanceSpeed,
                "animationSpeedMiddle": Utils.animationSpeedMiddle,
                "progressBarAnimationSpeed": Utils.progressBarAnimationSpeed
            }
        }
        var enabled = ConfigManager.getSettings().animationEnabled !== false
        for (var key in compact._animDefaults) {
            Utils[key] = enabled ? compact._animDefaults[key] : 0
        }
    }

    // ------------------------------------------------------------------
    // 界面
    // ------------------------------------------------------------------
    Item {
        anchors.fill: parent

        Rectangle {
            id: card
            anchors.fill: parent
            radius: compact.cardRadius
            // 上了亚克力就走「几乎全透」，让系统的模糊透上来；否则退回半透明纯色。
            // 不描边：窗口的圆角与材质归 DWM 管，卡片只负责填色，边界由材质自己
            // 的明暗变化表达。
            color: Qt.rgba(Theme.currentTheme.colors.backgroundColor.r,
                           Theme.currentTheme.colors.backgroundColor.g,
                           Theme.currentTheme.colors.backgroundColor.b,
                           compact.acrylicActive ? 0.22 : 0.94)
        }

        ColumnLayout {
            anchors.fill: card
            anchors.margins: compact.contentMargin
            spacing: 10

            // ── 标题条 ──
            Item {
                id: titleBar
                Layout.fillWidth: true
                Layout.preferredHeight: 44

                RowLayout {
                    anchors.fill: parent
                    spacing: 10

                    // 应用自己的图标，不加底板；右边跟着「启动台」三个字。
                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        iconKey: "url:" + Qt.resolvedUrl("../assets/icon.png")
                        iconSize: 28
                    }

                    Text {
                        Layout.alignment: Qt.AlignVCenter
                        // objectName 给无头验收脚本定位用。
                        objectName: "compactTitle"
                        font.pixelSize: 17
                        font.bold: true
                        color: Theme.currentTheme.colors.textColor
                        text: qsTr("启动台")
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            // ── 面板：双行格子板（最多 10 格） ──
            CompactPanel {
                id: panel
                objectName: "panel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 104
                slots: compact.panelSlots
                onActivated: compact.runSlot(slot)
                onMenuRequested: compact.showSlotMenu(slot, sceneX, sceneY)
            }

            // ── 第三行：存储位置 + 磁盘入口 ──
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 72

                Flickable {
                    id: storageRow
                    objectName: "storageRow"

                    anchors.fill: parent
                    clip: true
                    contentWidth: storageContent.implicitWidth
                    contentHeight: height
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentWidth > width + 1

                    Row {
                        id: storageContent

                        x: Math.max(0, (storageRow.width - implicitWidth) / 2)
                        y: Math.max(0, (storageRow.height - implicitHeight) / 2)
                        spacing: 8

                        // 固定的存储卡片（不是槽位，第三行的头一张）。宽度按行宽留出
                        // 一个磁盘卡的位置，两个 132 的卡片加间距刚好不溢出。
                        Frame {
                            width: 202
                            height: 66

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: compact.openStorage()
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                anchors.topMargin: 8
                                anchors.bottomMargin: 8
                                spacing: 10

                                AppIcon {
                                    Layout.alignment: Qt.AlignVCenter
                                    iconKey: "ic_fluent_storage_20_regular"
                                    iconSize: 24
                                    tint: Theme.currentTheme.colors.primaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 3

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Text {
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                            font.pixelSize: 12
                                            font.bold: true
                                            color: Theme.currentTheme.colors.textColor
                                            text: compact.storage.label || qsTr("存储位置")
                                        }

                                        Text {
                                            font.pixelSize: 10
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            // 这一行很窄：带上总量会把左边的目录名挤成
                                            // 「w...e」，总量留给提示气泡，进度条本身也表达了占比。
                                            text: compact.storage.available
                                                ? qsTr("剩余 %1").arg(compact.storage.free)
                                                : qsTr("容量未知")
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 4
                                        radius: 2
                                        color: Theme.currentTheme.colors.controlSecondaryColor

                                        Rectangle {
                                            height: parent.height
                                            radius: parent.radius
                                            width: parent.width * Math.min(100,
                                                Math.max(0, compact.storage.percent || 0)) / 100
                                            color: Theme.currentTheme.colors.primaryColor
                                        }
                                    }
                                }
                            }

                            ToolTip.text: compact.storage.available
                                ? qsTr("%1\n剩余 %2 / 共 %3")
                                    .arg(compact.storage.path)
                                    .arg(compact.storage.free)
                                    .arg(compact.storage.total)
                                : String(compact.storage.path || "")
                        }

                        // 磁盘槽位：U 盘与「指定的硬盘」是各自独立的两格。
                        Repeater {
                            model: compact.storageSlots

                            delegate: Frame {
                                id: diskCard

                                width: Math.min(214, Math.max(132, diskLabel.implicitWidth + 76))
                                height: 66
                                opacity: modelData.exists === false ? 0.55 : 1

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    onClicked: {
                                        if (mouse.button === Qt.LeftButton) {
                                            compact.runSlot(modelData)
                                        }
                                    }
                                    onPressed: {
                                        var scene = diskCard.mapToItem(null, mouse.x, mouse.y)
                                        compact.pendingPoint = Qt.point(scene.x, scene.y)
                                    }
                                    onReleased: {
                                        if (mouse.button === Qt.RightButton) {
                                            compact.showSlotMenu(modelData,
                                                                 compact.pendingPoint.x,
                                                                 compact.pendingPoint.y)
                                        }
                                    }
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    spacing: 10

                                    AppIcon {
                                        Layout.alignment: Qt.AlignVCenter
                                        iconKey: modelData.icon || ""
                                        iconSize: 22
                                        tint: modelData.exists === false
                                            ? Theme.currentTheme.colors.textSecondaryColor
                                            : Theme.currentTheme.colors.primaryColor
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 1

                                        Text {
                                            id: diskLabel
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                            font.pixelSize: 12
                                            font.bold: true
                                            color: Theme.currentTheme.colors.textColor
                                            text: modelData.name || qsTr("磁盘")
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            elide: Text.ElideMiddle
                                            font.pixelSize: 10
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            text: modelData.exists === false
                                                ? (modelData.kind === "usb"
                                                    ? qsTr("没有检测到")
                                                    : qsTr("路径不可用"))
                                                : String(modelData.path || "")
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── 底部操作条 ──
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                spacing: 6

                Button {
                    Layout.fillWidth: true
                    text: qsTr("打开完整窗口")
                    icon.name: "ic_fluent_window_20_regular"
                    onClicked: compact.openMain("launcher")
                }

                ToolButton {
                    icon.name: "ic_fluent_apps_20_regular"
                    ToolTip.text: qsTr("启动台设置")
                    onClicked: compact.openMain("launcher")
                }

                ToolButton {
                    icon.name: "ic_fluent_flash_20_regular"
                    ToolTip.text: qsTr("快捷操作")
                    onClicked: compact.openMain("records")
                }

                ToolButton {
                    icon.name: "ic_fluent_settings_20_regular"
                    ToolTip.text: qsTr("设置")
                    onClicked: compact.openMain("settings")
                }

                ToolButton {
                    icon.name: "ic_fluent_more_vertical_20_regular"
                    objectName: "compactMoreButton"
                    ToolTip.text: qsTr("更多")
                    onClicked: {
                        // position 必须是 None，否则 RinUI 的 Menu 会按锚点重算
                        // posX/posY，覆盖掉 popup() 指定的坐标。
                        var scene = parent.mapToItem(null, 0, 0)
                        moreMenu.popup(Qt.point(scene.x, scene.y + parent.height + 4))
                    }
                }
            }
        }

        // 简易 toast：常驻小窗没有 FloatLayer 那种容器，自绘一条更合适。
        Rectangle {
            id: toast

            anchors.horizontalCenter: card.horizontalCenter
            anchors.bottom: card.bottom
            anchors.bottomMargin: 52
            z: 900
            width: Math.min(toastText.implicitWidth + 24, card.width - 32)
            height: 32
            radius: 8
            color: Theme.currentTheme.colors.primaryColor
            opacity: 0
            visible: opacity > 0

            Behavior on opacity {
                NumberAnimation { duration: 160 }
            }

            Text {
                id: toastText
                anchors.centerIn: parent
                width: parent.width - 20
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                color: "white"
                font.pixelSize: 12
                text: ""
            }

            Timer {
                id: toastTimer
                interval: 2600
                onTriggered: toast.opacity = 0
            }
        }

        // 提权前确认层：小窗不接受键盘焦点，用自绘卡片而不是 Dialog；
        // 遮罩拦住底下的点击，点遮罩等于取消。
        Rectangle {
            id: adminConfirmScrim

            objectName: "adminConfirmScrim"
            anchors.fill: parent
            z: 950
            color: Qt.rgba(0, 0, 0, 0.35)
            opacity: 0
            visible: opacity > 0
            Behavior on opacity {
                NumberAnimation { duration: 140 }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: compact.cancelAdminRun()
            }

            Frame {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(parent.width - 48, 320)
                implicitHeight: confirmColumn.implicitHeight + 24
                hoverable: false

                ColumnLayout {
                    id: confirmColumn
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.textColor
                        font.pixelSize: 13
                        text: qsTr("以管理员身份运行：")
                    }
                    Text {
                        id: adminConfirmName
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.textColor
                        font.pixelSize: 13
                        font.bold: true
                        text: ""
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.currentTheme.colors.textSecondaryColor
                        font.pixelSize: 11
                        text: qsTr("会弹出 UAC 授权窗口。")
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Item { Layout.fillWidth: true }
                        Button {
                            text: qsTr("取消")
                            onClicked: compact.cancelAdminRun()
                        }
                        Button {
                            text: qsTr("运行")
                            highlighted: true
                            onClicked: compact.confirmAdminRun()
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // 菜单
    // ------------------------------------------------------------------
    // 某一格的右键菜单：先是最常用的「打开」，再是编辑入口。
    Menu {
        id: slotMenu

        position: Position.None
        property var slot: null

        MenuItem {
            text: slotMenu.slot && slotMenu.slot.kind === "usb"
                ? qsTr("打开可移动磁盘")
                : slotMenu.slot && slotMenu.slot.kind === "path"
                    ? qsTr("打开这个位置")
                    : qsTr("打开")
            icon.name: "ic_fluent_open_20_regular"
            onTriggered: compact.runSlot(slotMenu.slot)
        }

        MenuItem {
            text: qsTr("以管理员身份打开")
            icon.name: "ic_fluent_shield_20_regular"
            visible: !!slotMenu.slot && slotMenu.slot.kind === "action"
                && (slotMenu.slot.type === "file" || slotMenu.slot.type === "cmd")
            onTriggered: compact.runSlotAsAdmin(slotMenu.slot)
        }

        MenuSeparator {}

        MenuItem {
            text: qsTr("编辑这一格…")
            icon.name: "ic_fluent_edit_20_regular"
            enabled: !!slotMenu.slot
            onTriggered: compact.editSlot(slotMenu.slot)
        }
        MenuItem {
            text: qsTr("再加一格…")
            icon.name: "ic_fluent_add_20_regular"
            onTriggered: compact.addSlotToRow(slotMenu.slot)
        }
    }

    Menu {
        id: moreMenu

        position: Position.None

        MenuItem {
            text: qsTr("启动台设置…")
            icon.name: "ic_fluent_apps_20_regular"
            onTriggered: compact.openMain("launcher")
        }
        MenuItem {
            text: qsTr("快捷操作…")
            icon.name: "ic_fluent_flash_20_regular"
            onTriggered: compact.openMain("records")
        }
        MenuItem {
            text: qsTr("设置…")
            icon.name: "ic_fluent_settings_20_regular"
            onTriggered: compact.openMain("settings")
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("刷新磁盘信息")
            icon.name: "ic_fluent_arrow_sync_20_regular"
            onTriggered: ConfigManager.refreshStorageInfo()
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("隐藏小窗")
            icon.name: "ic_fluent_eye_off_20_regular"
            onTriggered: compact.hideRequested()
        }
        MenuItem {
            text: qsTr("退出")
            icon.name: "ic_fluent_power_20_regular"
            onTriggered: compact.quitRequested()
        }
    }

    // 右键那一刻的场景坐标，供菜单定位。
    property point pendingPoint: Qt.point(0, 0)

    Component.onCompleted: {
        snapToCorner()
        reload()
        applyAnimationSetting()
    }

    Connections {
        target: ConfigManager

        // 只有小窗关心的那一块变了才重取，设置改动不会带着这里一起重算。
        function onLauncherChanged() {
            compact.reload()
        }

        function onSettingsChanged() {
            // 动画总开关变化即时生效。
            compact.applyAnimationSetting()
        }

        function onShowToast(message, _severity) {
            toastText.text = message
            toast.opacity = 1
            toastTimer.restart()
        }
    }

    // ------------------------------------------------------------------
    // 数据
    // ------------------------------------------------------------------
    function reload() {
        // 一次取回全部槽位再按块分 —— 重复调用 getLauncherSlots() 会重复解析。
        var slots = ConfigManager.getLauncherSlots()
        panelSlots = filterRow(slots, 0)
        storageSlots = filterRow(slots, 1)
        storage = ConfigManager.getStorageInfo()
    }

    function filterRow(slots, row) {
        return slots.filter(function (item) { return item.row === row })
    }

    // ------------------------------------------------------------------
    // 交互
    // ------------------------------------------------------------------
    // tool 类槽位牵扯窗口操作，由 QML 处理；其余交给后端。
    function runSlot(slot) {
        if (!slot) {
            return
        }
        if (slot.kind === "tool") {
            runTool(slot.key)
            return
        }
        // 管理员动作：设置里开着「提权前确认」就先问一句（右键显式提权不拦）。
        if (slot.admin === true
                && ConfigManager.getSettings().confirmAdminActions !== false) {
            compact.askAdminRun(slot)
            return
        }
        ConfigManager.runLauncherSlot(slot)
    }

    // ── 提权前确认层 ──
    property var _pendingAdminSlot: null

    function askAdminRun(slot) {
        _pendingAdminSlot = slot
        adminConfirmName.text = slot && slot.name ? slot.name : qsTr("这个动作")
        adminConfirmScrim.opacity = 1
    }

    function cancelAdminRun() {
        _pendingAdminSlot = null
        adminConfirmScrim.opacity = 0
    }

    function confirmAdminRun() {
        var slot = _pendingAdminSlot
        cancelAdminRun()
        if (slot) {
            ConfigManager.runLauncherSlot(slot)
        }
    }

    function runSlotAsAdmin(slot) {
        if (!slot || slot.kind !== "action") {
            return
        }
        // 把解析出来的完整动作字段带过去（类型 / 目标 / 参数 / 工作目录 / 按键
        // 序列），缺了会执行出不一样的结果。
        // 右键点名要的提权：带 _explicit_admin 标记，不受「提权前确认 / 自动提权」拦截。
        var payload = {
            "id": slot.ref || "",
            "name": slot.name,
            "type": slot.type,
            "target": slot.target,
            "arguments": slot.arguments || "",
            "working_dir": slot.working_dir || "",
            "keyboard_steps": slot.keyboard_steps || [],
            "run_as": "admin",
            "_explicit_admin": true
        }
        ConfigManager.executeAction(payload)
    }

    function runTool(key) {
        switch (key) {
        case "launcherPage":
            compact.openMain("launcher")
            break
        case "records":
            compact.openMain("records")
            break
        case "settings":
            compact.openMain("settings")
            break
        case "configFolder":
            ConfigManager.openConfigFolder()
            break
        case "configFile":
            ConfigManager.openConfigFile()
            break
        case "reload":
            ConfigManager.reloadConfig()
            break
        case "elevate":
            ConfigManager.restartAsAdmin()
            break
        case "hide":
            compact.hideRequested()
            break
        case "quit":
            compact.quitRequested()
            break
        }
    }

    function openStorage() {
        ConfigManager.openPath(compact.storage.path || "")
    }

    // 小窗是独立的 QML 根，够不到完整窗口，跨窗口的请求统一走信号交给 Python。
    function openMain(page) {
        compact.openMainRequested(page)
    }

    // 右键菜单的编辑入口：切到启动台页并当场打开这一格的编辑器。
    function editSlot(slot) {
        if (slot) {
            ConfigManager.requestSlotEditor(slot.row, slot.rowIndex)
        }
    }

    function addSlotToRow(slot) {
        ConfigManager.requestSlotEditor(slot ? slot.row : 0, -1)
    }

    function showSlotMenu(slot, sceneX, sceneY) {
        if (!slot) {
            return
        }
        slotMenu.slot = slot
        var local = compact.contentItem.mapFromItem(null, sceneX, sceneY)
        slotMenu.popup(Qt.point(local.x, local.y))
    }
}
