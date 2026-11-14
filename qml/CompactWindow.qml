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
import "dialogs"

// 常驻桌面右下角的启动台小窗。
//
// 三块内容（前两块都在完整窗口的「启动台」页里配）：
//   面板：最多 10 格的双行格子板（≤ 5 格一排，更多时平分两排）
//   存储区：存储卡片 + 磁盘入口
//   系统控制：系统音量 + Wi-Fi 开关 + 移动热点开关
// 窗口是「沉底」的桌面挂件：无边框、不抢焦点、不进任务栏，也不盖在别的窗口
// 之上 —— 它贴在主显示器右下角，被普通窗口盖住，像桌面上的一块部件。
// 高度固定为桌面可用高度的一半（见 rin_launcher/effects.py）。
//
// 界面按块拆在 components/ 下：CompactPanel（格子板）、CompactStorageRow
// （存储 + 磁盘）、SystemControlBar（音量 / Wi-Fi / 热点）、CompactMiniBar
// （迷你条）、CompactToast（自绘提示）。这里只留窗口形态、位置与交互。
Window {
    id: compact

    // ── 形态 ──
    // 窗口与卡片同尺寸：系统材质与圆角直接作用在窗口上，外面不套透明边，
    // 也就没有那一圈「玻璃边框」。投影交给系统，QML 不再自绘。
    readonly property int edgeMargin: 16      // 贴边时与桌面边缘的距离
    readonly property int contentMargin: 16   // 卡片内的内容留白
    // 圆角直接用 RinUI 主题令牌（Win11 默认 8px），不另起一套数值。
    readonly property int cardRadius: Theme.currentTheme.appearance.windowRadius
    // 两种形态各用各的圆角：完整窗口跟系统令牌，迷你条做成胶囊。
    readonly property int surfaceRadius: miniMode
        ? Math.round(height / 2) : cardRadius

    // normal = 完整启动台；mini = 单行工具条。
    property string windowMode: "normal"
    property string windowCorner: "bottom-right"
    property int offsetX: 0
    property int offsetY: 0
    property int compactTransparency: 82
    property int miniTransparency: 30

    readonly property bool normalMode: windowMode === "normal"
    readonly property bool miniMode: windowMode === "mini"
    readonly property int transparencyValue: miniMode
        ? miniTransparency : compactTransparency
    // 透明度越大越透；保留 8% 下限，避免文字完全浮在壁纸上。
    readonly property real cardAlpha: Math.max(0.08,
        (100 - Math.max(0, Math.min(90, transparencyValue))) / 100)

    // 迷你条：3×44 图标 + 2×96 存储卡 + 36 更多 + 内外边距与间距。
    width: normalMode ? 400 : 404
    // 主屏可用高度由 Python 注入（多显示器下 Screen.* 会跟着窗口所在屏幕跑，
    // 不能用来算「主屏的一半」）。没注入时退回 Screen 的单屏行为。
    property int primaryX: 0
    property int primaryY: 0
    property int primaryWidth: 0
    property int primaryHeight: 0
    readonly property int availableHeight: primaryHeight > 0
        ? primaryHeight : Screen.desktopAvailableHeight
    height: normalMode ? Math.max(400, Math.round(availableHeight / 2)) : 56
    visible: false
    color: "transparent"
    title: qsTr("启动台")
    // 无边框 + 工具窗口（不占任务栏）+ 不接受焦点 + 全局置底。置底由这里声明，
    // Python 侧显示时再用 SetWindowPos(HWND_BOTTOM) 兜一次底
    // （见 effects.apply_bottom_layer）。
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnBottomHint

    // 是否成功套上 RinUI 云母 / 增强云母（由 Python 在应用材质后 setProperty 进来）。
    // 没上成功就把卡片画实一点，免得在透明背景上看着发虚。
    property bool backdropActive: false

    // 强调色是全局设置，但 Theme/Utils 是每个 QML 引擎各自的单例：新窗口创建时
    // 应用一次，之后靠 ConfigManager 的信号让三个窗口一起变。
    function applyAccentColor() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var value = ConfigManager.accentColor
        if (value && value.length > 0) {
            Utils.primaryColor = value
        }
    }

    function applyThemeSetting() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var mode = String(ConfigManager.getSettings().theme || "system")
        Theme.setTheme(mode === "light" ? Theme.mode.Light
                      : mode === "dark" ? Theme.mode.Dark
                      : Theme.mode.Auto)
    }

    // ── 状态 ──
    property var panelSlots: []
    property var storageSlots: []
    property var storage: ({})
    property var usbDevices: []
    // 全局磁贴尺寸档位：small / medium / large。
    property string tileSizeMode: "medium"
    // 面板 + 存储行的内容签名：一致就不重建格子，避免每 2.5 秒闪一下。
    property string slotsSignature: ""

    function applyTileSize() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var value = String(ConfigManager.getSettings().tileSize || "medium")
        tileSizeMode = ["small", "medium", "large"].indexOf(value) >= 0
            ? value : "medium"
    }

    // 小窗只发信号，窗口切换 / 退出这类跨窗口的活儿统一交给 Python 决定。
    signal openMainRequested(string page)
    signal hideRequested()
    signal quitRequested()

    // ------------------------------------------------------------------
    // 位置：固定贴主显示器右下角，不拖动、不记忆。
    // ------------------------------------------------------------------
    function snapToCorner() {
        // 多显示器下 Screen.virtualX + desktopAvailableWidth 算出来的是**虚拟桌面**
        // 的右边缘，窗口会跑到最右侧那块屏上。主屏几何由 Python 注入，拿不到时
        // 才退回单屏公式（主屏位于虚拟桌面原点时两者等价）。
        var left = primaryX
        var right = primaryX + primaryWidth
        var bottom = primaryY + primaryHeight
        if (primaryWidth <= 0 || primaryHeight <= 0) {
            left = Screen.virtualX
            right = Screen.virtualX + Screen.desktopAvailableWidth
            bottom = Screen.virtualY + Screen.desktopAvailableHeight
        }
        // 贴左上角或右上角，两种形态都适用。
        if (windowCorner !== "bottom-left") {
            x = right - width - edgeMargin + offsetX
        } else {
            x = left + edgeMargin + offsetX
        }
        y = bottom - height - edgeMargin + offsetY
    }

    function applyWindowSettings() {
        if (typeof ConfigManager === "undefined" || !ConfigManager) {
            return
        }
        var settings = ConfigManager.getSettings()
        var mode = String(settings.compactMode || "normal")
        windowMode = mode === "mini" ? "mini" : "normal"
        windowCorner = String(settings.windowCorner || "bottom-right")
        offsetX = Number(settings.windowOffsetX || 0)
        offsetY = Number(settings.windowOffsetY || 0)
        compactTransparency = Number(settings.compactTransparency)
        miniTransparency = Number(settings.miniTransparency)
        if (isNaN(compactTransparency)) compactTransparency = 82
        if (isNaN(miniTransparency)) miniTransparency = 30
        snapToCorner()
    }

    function setWindowMode(mode) {
        if (["normal", "mini"].indexOf(mode) < 0 || mode === windowMode) {
            return
        }
        ConfigManager.updateSettings({ "compactMode": mode })
    }

    // 显示时贴回角落；分辨率 / 任务栏变化时窗口高度会跟着变，顺带重贴一次。
    onVisibleChanged: {
        if (visible) {
            snapToCorner()
        }
    }
    onHeightChanged: snapToCorner()
    onWidthChanged: snapToCorner()
    onWindowModeChanged: snapToCorner()

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
            radius: compact.surfaceRadius
            // 上了云母就走用户设定的透明度，让材质透上来；没上材质时留一个
            // 不透明下限，避免文字直接铺在壁纸上。
            color: Qt.rgba(Theme.currentTheme.colors.backgroundColor.r,
                           Theme.currentTheme.colors.backgroundColor.g,
                           Theme.currentTheme.colors.backgroundColor.b,
                           compact.backdropActive
                               ? compact.cardAlpha
                               : Math.max(0.62, compact.cardAlpha))
            border.width: 0
        }

        ColumnLayout {
            anchors.fill: card
            anchors.margins: compact.contentMargin
            visible: compact.normalMode
            spacing: 12

            // ── 标题条 ──
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 48

                RowLayout {
                    anchors.fill: parent
                    spacing: 8

                    // 应用自己的图标，不加底板；右边跟着「启动台」三个字。
                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        iconKey: "url:" + Qt.resolvedUrl("../assets/icon.png")
                        iconSize: 24
                    }

                    Text {
                        Layout.alignment: Qt.AlignVCenter
                        // objectName 给无头验收脚本定位用。
                        objectName: "compactTitle"
                        // 用 RinUI 的 Body Strong 尺寸，标题不靠大字号撑场面。
                        font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                        font.weight: Font.DemiBold
                        color: Theme.currentTheme.colors.textColor
                        text: qsTr("启动台")
                    }

                    Item { Layout.fillWidth: true }

                    ToolButton {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        icon.name: "ic_fluent_edit_20_regular"
                        ToolTip.text: qsTr("编辑启动台")
                        ToolTip.visible: hovered
                        ToolTip.delay: 500
                        onClicked: compact.openMain("launcher")
                    }

                    ToolButton {
                        id: moreButton
                        objectName: "compactMoreButton"
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        icon.name: "ic_fluent_more_vertical_20_regular"
                        ToolTip.text: qsTr("更多")
                        ToolTip.visible: hovered
                        ToolTip.delay: 500
                        onClicked: compact.popupMoreMenu(moreButton)
                    }
                }

                // 标题与内容之间的发丝线：Win11 的标题区就是靠一条 1px 分隔线定界。
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.currentTheme.colors.dividerBorderColor
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
                sizeMode: compact.tileSizeMode
                onActivated: compact.runSlot(slot)
            }

            // ── 第三行：存储位置 + 磁盘入口 ──
            CompactStorageRow {
                Layout.fillWidth: true
                storage: compact.storage
                slots: compact.storageSlots
                onStorageActivated: compact.openStorage()
                onSlotActivated: compact.runSlot(slot)
            }

            // ── 底部：系统控制（音量 / Wi-Fi / 热点） ──
            SystemControlBar {
                objectName: "systemControlBar"
                Layout.fillWidth: true
                Layout.preferredHeight: 66
            }
        }

        // ──────────────────────────────────────────────────────────
        // 迷你模式：单行工具条
        // ──────────────────────────────────────────────────────────
        CompactMiniBar {
            anchors.fill: parent
            visible: compact.miniMode
            panelSlots: compact.panelSlots
            storage: compact.storage
            usbDevices: compact.usbDevices
            onSlotActivated: compact.runSlot(slot)
            onStorageActivated: compact.openStorage()
            onMoreRequested: compact.popupMoreMenu(anchor)
        }

        // 常驻小窗没有 FloatLayer 那种容器，自绘一条提示更合适。
        CompactToast {
            id: toast
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            // 完整模式给底部系统控制条留位置；迷你条贴着卡片底部即可。
            anchors.bottomMargin: compact.normalMode ? 128 : 6
        }
    }


    // ------------------------------------------------------------------
    // 菜单
    // ------------------------------------------------------------------
    // 小窗菜单统一用独立窗口渲染：QQC2 的 Menu 在置底无焦点窗口上会被 Qt
    // 立刻关掉、坐标也会被重置，做不出可用的浮层。
    CompactMenuWindow {
        id: compactMenu
    }

    function menuArea() {
        var width = primaryWidth > 0 ? primaryWidth : Screen.desktopAvailableWidth
        var height = primaryHeight > 0 ? primaryHeight : Screen.desktopAvailableHeight
        var x = primaryWidth > 0 ? primaryX : Screen.virtualX
        var y = primaryHeight > 0 ? primaryY : Screen.virtualY
        return Qt.rect(x, y, width, height)
    }

    // 磁盘 / U 盘是热插拔的：小窗可见时每 2.5 秒重读一次（隐藏时停掉）。
    Timer {
        interval: 2500
        repeat: true
        running: compact.visible
        onTriggered: compact.refreshLive()
    }

    Component.onCompleted: {
        applyWindowSettings()
        reload()
        applyAnimationSetting()
        applyAccentColor()
        applyThemeSetting()
        applyTileSize()
        snapToCorner()
    }

    Connections {
        target: ConfigManager

        // 只有小窗关心的那一块变了才重取，设置改动不会带着这里一起重算。
        function onLauncherChanged() {
            compact.reload()
        }

        function onSettingsChanged() {
            // 动画总开关、磁贴尺寸、形态 / 位置 / 透明度即时生效。
            compact.applyAnimationSetting()
            compact.applyTileSize()
            compact.applyWindowSettings()
            compact.applyThemeSetting()
        }

        // 强调色 / 整份配置变化：每个窗口是独立 QML 引擎，都要各自更新。
        function onAccentColorChanged() { compact.applyAccentColor() }
        function onConfigChanged() { compact.applyAccentColor() }

        function onShowToast(message, _severity) {
            toast.show(message)
        }
    }

    // ------------------------------------------------------------------
    // 数据
    // ------------------------------------------------------------------
    function reload() {
        // 一次取回全部槽位再按块分 —— 重复调用 getLauncherSlots() 会重复解析。
        var slots = ConfigManager.getLauncherSlots()
        slotsSignature = slotSignature(slots)
        panelSlots = filterRow(slots, 0)
        storageSlots = filterRow(slots, 1)
        storage = ConfigManager.getStorageInfo()
        usbDevices = ConfigManager.getRemovableDevices()
    }

    // 老数组和新数组的「可显示信息」一致时就不重建格子，避免每 2.5 秒闪烁。
    function slotSignature(slots) {
        // free / percent 必须进签名：U 盘和 path 磁盘卡的容量文字直接绑定
        // 这两个字段，只比较名称/路径会让它们停在插上时的旧值。
        return slots.map(function (slot) {
            return [slot.kind, slot.name, slot.path, slot.icon,
                    slot.enabled === false ? 0 : 1,
                    slot.available === false ? 0 : 1,
                    slot.free || "", slot.total || "",
                    slot.percent || 0].join("|")
        }).sort().join("\n")
    }

    function refreshLive() {
        storage = ConfigManager.refreshStorageInfo()
        var slots = ConfigManager.getLauncherSlots()
        var signature = slotSignature(slots)
        if (signature !== compact.slotsSignature) {
            compact.slotsSignature = signature
            panelSlots = filterRow(slots, 0)
            storageSlots = filterRow(slots, 1)
        }
        usbDevices = ConfigManager.getRemovableDevices()
    }

    // 退出 / 提权两类确认都是屏幕正中的独立置顶窗口，小窗里不留遮罩。
    property ConfirmDialog quitConfirmDialog: ConfirmDialog {}
    property ConfirmDialog adminConfirmDialog: ConfirmDialog {}

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
        // 管理员动作：设置里开着「提权前确认」就先问一句。
        if (slot.admin === true
                && ConfigManager.getSettings().confirmAdminActions !== false) {
            compact.askAdminRun(slot)
            return
        }
        ConfigManager.runLauncherSlot(slot)
    }

    function askQuit() {
        quitConfirmDialog.ask(qsTr("确认退出？查理会想你的。"), function () {
            compact.quitRequested()
        }, { confirmText: qsTr("动手！") })
    }

    // 提权前确认：独立弹窗，确认后把完整动作交给后端（UAC 由后端弹）。
    property var _pendingAdminSlot: null

    function askAdminRun(slot) {
        _pendingAdminSlot = slot
        var name = slot && slot.name ? slot.name : qsTr("这个动作")
        adminConfirmDialog.ask(
            qsTr("以管理员身份运行「%1」？会弹出 UAC 授权窗口。").arg(name),
            function () {
                var target = _pendingAdminSlot
                _pendingAdminSlot = null
                if (target) {
                    ConfigManager.runLauncherSlot(target)
                }
            },
            { confirmText: qsTr("运行") })
    }

    function runTool(key) {
        switch (key) {
        case "launcherPage":
            compact.openMain("launcher")
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

    // 菜单内容一律走独立窗口；屏幕坐标 = 窗口坐标 + 场景坐标。
    function popupMoreMenu(anchor) {
        var item = anchor || moreButton
        var scene = item.mapToItem(null, item.width, 0)
        var list = []
        if (!compact.normalMode) {
            list.push({ icon: "ic_fluent_edit_20_regular", text: qsTr("编辑启动台"),
                        action: function () { compact.openMain("launcher") } })
            list.push({ icon: "ic_fluent_desktop_20_regular", text: qsTr("完整模式"),
                        action: function () { compact.setWindowMode("normal") } })
        }
        if (compact.windowMode !== "mini") {
            list.push({ icon: "ic_fluent_dock_row_20_regular", text: qsTr("迷你模式"),
                        action: function () { compact.setWindowMode("mini") } })
        }
        list.push({ separator: true })
        list.push({ icon: "ic_fluent_settings_20_regular", text: qsTr("打开设置"),
                    action: function () { compact.openMain("settings") } })
        list.push({ separator: true })
        list.push({ icon: "ic_fluent_arrow_sync_20_regular", text: qsTr("重启"),
                    action: function () { ConfigManager.restartApplication() } })
        list.push({ icon: "ic_fluent_shield_20_regular", text: qsTr("提权重启"),
                    action: function () { ConfigManager.restartAsAdmin() } })
        list.push({ separator: true })
        list.push({ icon: "ic_fluent_wrench_screwdriver_20_regular", text: qsTr("恢复模式"),
                    action: function () { ConfigManager.restartWithMode("recovery") } })
        list.push({ separator: true })
        list.push({ icon: "ic_fluent_eye_off_20_regular", text: qsTr("隐藏小窗"),
                    action: function () { compact.hideRequested() } })
        list.push({ icon: "ic_fluent_power_20_regular", text: qsTr("退出"),
                    action: function () { compact.askQuit() } })
        compactMenu.openAt(compact.x + scene.x, compact.y + scene.y, list, menuArea())
    }

}
