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
Window {
    id: compact

    // ── 形态 ──
    // 窗口与卡片同尺寸：系统材质与圆角直接作用在窗口上，外面不套透明边，
    // 也就没有那一圈「玻璃边框」。投影交给系统，QML 不再自绘。
    readonly property int edgeMargin: 16      // 贴边时与桌面边缘的距离
    readonly property int contentMargin: 16   // 卡片内的内容留白
    // 圆角直接用 RinUI 主题令牌（Win11 默认 8px），不另起一套数值。
    readonly property int cardRadius: Theme.currentTheme.appearance.windowRadius
    // 三种形态各用各的圆角：完整窗口跟系统令牌，迷你条做成胶囊，悬浮球保持圆形。
    readonly property int surfaceRadius: floatingMode ? 36
        : miniMode ? Math.round(height / 2) : cardRadius

    // ── 形态 ──
    // normal = 完整启动台；mini = 单行工具条；floating = 右下角悬浮球。
    property string windowMode: "normal"
    property string windowCorner: "bottom-right"
    property int offsetX: 0
    property int offsetY: 0
    property int compactTransparency: 82
    property int miniTransparency: 30
    property int floatingTransparency: 8
    property bool ballExpanded: false

    readonly property bool normalMode: windowMode === "normal"
    readonly property bool miniMode: windowMode === "mini"
    readonly property bool floatingMode: windowMode === "floating"
    readonly property int transparencyValue: miniMode ? miniTransparency
        : floatingMode ? floatingTransparency : compactTransparency
    // 透明度越大越透；保留 8% 下限，避免文字完全浮在壁纸上。
    readonly property real cardAlpha: Math.max(0.08,
        (100 - Math.max(0, Math.min(90, transparencyValue))) / 100)

    // 迷你条：3×44 图标 + 2×96 存储卡 + 36 更多 + 内外边距与间距。
    width: normalMode ? 400 : (miniMode ? 404 : 72)
    // 主屏可用高度由 Python 注入（多显示器下 Screen.* 会跟着窗口所在屏幕跑，
    // 不能用来算「主屏的一半」）。没注入时退回 Screen 的单屏行为。
    property int primaryX: 0
    property int primaryY: 0
    property int primaryWidth: 0
    property int primaryHeight: 0
    readonly property int availableHeight: primaryHeight > 0
        ? primaryHeight : Screen.desktopAvailableHeight
    height: normalMode ? Math.max(400, Math.round(availableHeight / 2))
        : miniMode ? 56
        : (ballExpanded ? 216 : 72)
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

    // ── 状态 ──
    property var panelSlots: []
    property var storageSlots: []
    property var storage: ({})
    property var usbDevices: []
    // 全局磁贴尺寸档位：small / medium / large。
    property string tileSizeMode: "medium"

    // 存储行卡片宽度：单卡铺开，两张平分，再多就固定 160 起横向滚动。
    // 之前统一 202，两张卡（存储 + 一个磁盘）就会顶出可视区、还剩半截在滚动里。
    readonly property real storageCardWidth: {
        var count = 1 + storageSlots.length
        if (count <= 1) {
            return Math.min(320, storageRow.width)
        }
        return Math.max(160, Math.min(202,
            (storageRow.width - (count - 1) * 8) / count))
    }

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
        // 悬浮球始终贴在右下角，不受窗口位置设置影响。
        if (floatingMode || windowCorner !== "bottom-left") {
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
        windowMode = ["normal", "mini", "floating"].indexOf(mode) >= 0 ? mode : "normal"
        windowCorner = String(settings.windowCorner || "bottom-right")
        offsetX = Number(settings.windowOffsetX || 0)
        offsetY = Number(settings.windowOffsetY || 0)
        compactTransparency = Number(settings.compactTransparency)
        miniTransparency = Number(settings.miniTransparency)
        floatingTransparency = Number(settings.floatingTransparency)
        if (isNaN(compactTransparency)) compactTransparency = 82
        if (isNaN(miniTransparency)) miniTransparency = 30
        if (isNaN(floatingTransparency)) floatingTransparency = 8
        if (!floatingMode) {
            ballExpanded = false
        }
        snapToCorner()
    }

    function setWindowMode(mode) {
        if (["normal", "mini", "floating"].indexOf(mode) < 0 || mode === windowMode) {
            return
        }
        ballExpanded = false
        ConfigManager.updateSettings({ "compactMode": mode })
    }

    // 显示时贴回角落；分辨率 / 任务栏变化时窗口高度会跟着变，顺带重贴一次。
    onVisibleChanged: {
        if (visible) {
            snapToCorner()
        } else {
            // 隐藏时收起悬浮球，免得全局 Esc / 点外部监听一直挂着。
            ballExpanded = false
        }
    }
    onHeightChanged: snapToCorner()
    onWidthChanged: snapToCorner()
    onWindowModeChanged: {
        ballExpanded = false
        snapToCorner()
    }
    onBallExpandedChanged: {
        if (floatingMode && typeof FloatingBall !== "undefined" && FloatingBall) {
            FloatingBall.setActive(ballExpanded)
        }
        snapToCorner()
    }

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
            color: compact.floatingMode
                ? "transparent"
                : Qt.rgba(Theme.currentTheme.colors.backgroundColor.r,
                          Theme.currentTheme.colors.backgroundColor.g,
                          Theme.currentTheme.colors.backgroundColor.b,
                          compact.backdropActive
                              ? compact.cardAlpha
                              : Math.max(0.62, compact.cardAlpha))
            border.width: 0
        }

        ColumnLayout {
            id: normalContent
            anchors.fill: card
            anchors.margins: compact.contentMargin
            visible: compact.normalMode
            spacing: 12

            // ── 标题条 ──
            Item {
                id: titleBar
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
                        id: editButton
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

                        // 固定的存储卡片（不是槽位，第三行的头一张）。
                        // 只有这一张时铺开占满整行，配了磁盘卡之后再退回等宽，
                        // 免得右边空一大块、或者单卡被 202 卡住溢出滚动。
                        Frame {
                            width: compact.storageCardWidth
                            height: 66
                            padding: 0
                            radius: compact.cardRadius
                            // 云母已经定义了卡片的边界，再描一圈边就显得脏。
                            border.width: 0

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
                                    tint: Theme.currentTheme.colors.textColor
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
                                            font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                                            font.weight: Font.DemiBold
                                            color: Theme.currentTheme.colors.textColor
                                            text: compact.storage.label || qsTr("存储位置")
                                        }

                                        Text {
                                            font.pixelSize: Theme.currentTheme.typography.captionSize
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
                                        Layout.preferredHeight: 6
                                        radius: 3
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

                                width: compact.storageCardWidth
                                height: 66
                                padding: 0
                                radius: Theme.currentTheme.appearance.windowRadius
                                border.width: 0
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
                                        iconSize: 24
                                        tint: modelData.exists === false
                                            ? Theme.currentTheme.colors.textSecondaryColor
                                            : Theme.currentTheme.colors.textColor
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 2

                                        Text {
                                            id: diskLabel
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                            font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                                            font.weight: Font.DemiBold
                                            color: Theme.currentTheme.colors.textColor
                                            text: modelData.name || qsTr("磁盘")
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            elide: Text.ElideMiddle
                                            font.pixelSize: Theme.currentTheme.typography.captionSize
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            text: compact.slotDetail(modelData)
                                        }

                                        // U 盘与磁盘都给出占用条；多分区容量由后端合并。
                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 4
                                            radius: 2
                                            visible: modelData.exists !== false
                                                && Number(modelData.percent || 0) > 0
                                            color: Theme.currentTheme.colors.controlSecondaryColor

                                            Rectangle {
                                                height: parent.height
                                                radius: parent.radius
                                                width: parent.width
                                                    * Math.min(100, Math.max(0,
                                                        Number(modelData.percent || 0))) / 100
                                                color: Theme.currentTheme.colors.primaryColor
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
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
        Item {
            id: miniContent
            anchors.fill: parent
            visible: compact.miniMode

            RowLayout {
                anchors.fill: parent
                anchors.margins: 6
                spacing: 6

                // 前三个固定应用：只显示图标，不显示文字。
                Repeater {
                    model: compact.panelSlots.slice(0, 3)

                    delegate: Frame {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        padding: 0
                        // 迷你条整体是胶囊，内部 44 高的卡片直接取半高做圆角。
                        radius: 22
                        border.width: 0
                        color: miniMouse.containsMouse
                            ? Theme.currentTheme.colors.subtleSecondaryColor
                            : Theme.currentTheme.colors.cardColor

                        AppIcon {
                            anchors.centerIn: parent
                            iconKey: modelData.icon || "ic_fluent_apps_20_regular"
                            iconSize: 22
                            tint: Theme.currentTheme.colors.textColor
                            placeholder: "ic_fluent_apps_20_regular"
                        }

                        MouseArea {
                            id: miniMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: {
                                if (mouse.button === Qt.LeftButton) {
                                    compact.runSlot(modelData)
                                } else {
                                    var scene = parent.mapToItem(null, mouse.x, mouse.y)
                                    compact.showSlotMenu(modelData, scene.x, scene.y)
                                }
                            }
                        }

                        ToolTip.text: modelData.name || ""
                        ToolTip.visible: miniMouse.containsMouse
                    }
                }

                // 固定存储位置：与 Wi-Fi 开关同样的卡片样式。
                Frame {
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 44
                    padding: 0
                    radius: 22
                    border.width: 0
                    color: storageMouse.containsMouse
                        ? Theme.currentTheme.colors.subtleSecondaryColor
                        : Theme.currentTheme.colors.cardColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: "ic_fluent_storage_20_regular"
                            iconSize: 20
                            tint: Theme.currentTheme.colors.textColor
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 0
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.captionSize
                                font.weight: Font.DemiBold
                                color: Theme.currentTheme.colors.textColor
                                text: compact.storage.label || qsTr("存储")
                            }
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.captionSize - 1
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: compact.storage.available
                                    ? qsTr("剩余 %1").arg(compact.storage.free)
                                    : qsTr("不可用")
                            }
                        }
                    }

                    MouseArea {
                        id: storageMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: compact.openStorage()
                    }
                    ToolTip.text: String(compact.storage.path || "")
                    ToolTip.visible: storageMouse.containsMouse
                }

                // U 盘快捷开关：没有设备时置灰禁用，不隐藏，位置稳定。
                Frame {
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 44
                    padding: 0
                    radius: 22
                    border.width: 0
                    opacity: compact.usbDevices.length > 0 ? 1 : 0.55
                    color: usbMouse.containsMouse && compact.usbDevices.length > 0
                        ? Theme.currentTheme.colors.subtleSecondaryColor
                        : Theme.currentTheme.colors.cardColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: "ic_fluent_usb_plug_20_regular"
                            iconSize: 20
                            tint: Theme.currentTheme.colors.textColor
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 0
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.captionSize
                                font.weight: Font.DemiBold
                                color: Theme.currentTheme.colors.textColor
                                text: compact.usbDevices.length > 0
                                    ? (compact.usbDevices[0].name || qsTr("U 盘"))
                                    : qsTr("U 盘")
                            }
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: Theme.currentTheme.typography.captionSize - 1
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: compact.usbDevices.length > 0
                                    ? qsTr("已用 %1%").arg(compact.usbDevices[0].percent || 0)
                                    : qsTr("没有检测到")
                            }
                        }
                    }

                    MouseArea {
                        id: usbMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: compact.usbDevices.length > 0
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: ConfigManager.openRemovableDrive()
                    }
                    ToolTip.text: compact.usbDevices.length > 0
                        ? qsTr("%1\n共 %2 · 剩余 %3 · %4 个分区")
                            .arg(compact.usbDevices[0].name || "U 盘")
                            .arg(compact.usbDevices[0].total || "?")
                            .arg(compact.usbDevices[0].free || "?")
                            .arg(compact.usbDevices[0].partitions.length)
                        : qsTr("没有检测到 U 盘")
                    ToolTip.visible: usbMouse.containsMouse
                }

                Item { Layout.fillWidth: true }

                ToolButton {
                    id: miniMoreButton
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    Layout.alignment: Qt.AlignVCenter
                    icon.name: "ic_fluent_more_vertical_20_regular"
                    ToolTip.text: qsTr("更多")
                    ToolTip.visible: hovered
                    onClicked: compact.popupMoreMenu(miniMoreButton)
                }
            }
        }

        // ──────────────────────────────────────────────────────────
        // 悬浮球：置底、无焦点、不可拖拽
        // ──────────────────────────────────────────────────────────
        Item {
            id: floatingContent
            anchors.fill: parent
            visible: compact.floatingMode

            // 点击展开区域内的空白处 = 点击菜单外部。
            MouseArea {
                anchors.fill: parent
                onClicked: compact.ballExpanded = false
            }

            Column {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.rightMargin: 4
                anchors.bottomMargin: 4
                spacing: 6

                Column {
                    visible: compact.ballExpanded
                    spacing: 6

                    Repeater {
                        model: [
                            { icon: "ic_fluent_desktop_20_regular", tip: qsTr("正常模式") },
                            { icon: "ic_fluent_dock_row_20_regular", tip: qsTr("迷你模式") },
                            { icon: "ic_fluent_more_horizontal_20_regular", tip: qsTr("更多") }
                        ]

                        delegate: Frame {
                            id: ballBtn
                            required property int index
                            required property var modelData
                            width: 44
                            height: 44
                            padding: 0
                            radius: 22
                            color: ballBtnMouse.containsMouse
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : Theme.currentTheme.colors.cardColor
                            border.width: 0
                            scale: ballBtnMouse.pressed ? 0.92
                                : (ballBtnMouse.containsMouse ? 1.06 : 1)

                            Behavior on scale {
                                NumberAnimation {
                                    duration: Utils.animationSpeedFaster
                                    easing.type: Easing.OutCubic
                                }
                            }

                            AppIcon {
                                anchors.centerIn: parent
                                iconKey: modelData.icon
                                iconSize: 20
                                tint: Theme.currentTheme.colors.textColor
                            }

                            MouseArea {
                                id: ballBtnMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (index === 0) {
                                        compact.setWindowMode("normal")
                                    } else if (index === 1) {
                                        compact.setWindowMode("mini")
                                    } else {
                                        compact.popupMoreMenu(ballBtn)
                                    }
                                }
                            }

                            ToolTip.text: modelData.tip
                            ToolTip.visible: ballBtnMouse.containsMouse
                        }
                    }
                }

                Frame {
                    width: 64
                    height: 64
                    padding: 0
                    radius: 32
                    color: Theme.currentTheme.colors.cardColor
                    // 悬停放大、按下回缩：置底窗口也能看出「点得到」。
                    scale: ballMouse.pressed ? 0.94
                        : (ballMouse.containsMouse ? 1.06 : 1)

                    Behavior on scale {
                        NumberAnimation {
                            duration: Utils.animationSpeedFaster
                            easing.type: Easing.OutCubic
                        }
                    }

                    AppIcon {
                        anchors.centerIn: parent
                        iconKey: "url:" + Qt.resolvedUrl("../assets/icon.png")
                        iconSize: 48
                    }

                    MouseArea {
                        id: ballMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: compact.ballExpanded = !compact.ballExpanded
                    }

                    ToolTip.text: compact.ballExpanded ? qsTr("收起") : qsTr("Rin Launcher")
                    ToolTip.visible: ballMouse.containsMouse
                }
            }
        }

        // 简易 toast：常驻小窗没有 FloatLayer 那种容器，自绘一条更合适。
        Rectangle {
            id: toast

            anchors.horizontalCenter: card.horizontalCenter
            anchors.bottom: card.bottom
            // 完整模式给底部系统控制条留位置；迷你 / 悬浮球贴着卡片底部即可。
            anchors.bottomMargin: compact.normalMode ? 128 : 6
            z: 900
            width: Math.min(toastText.implicitWidth + 24, card.width - 32)
            height: 32
            radius: Theme.currentTheme.appearance.windowRadius
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
                font.pixelSize: Theme.currentTheme.typography.captionSize
                text: ""
            }

            Timer {
                id: toastTimer
                interval: 2600
                onTriggered: toast.opacity = 0
            }
        }

        // 提权 / 退出确认已改成独立窗口（见文件末尾的 ConfirmDialog），小窗里不再自绘遮罩。
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
            text: qsTr("编辑启动台")
            icon.name: "ic_fluent_edit_20_regular"
            // 完整模式的编辑按钮就在标题栏；迷你 / 悬浮球里必须收进菜单。
            visible: !compact.normalMode
            onTriggered: compact.openMain("launcher")
        }
        MenuItem {
            text: qsTr("完整模式")
            icon.name: "ic_fluent_desktop_20_regular"
            visible: !compact.normalMode
            onTriggered: compact.setWindowMode("normal")
        }
        MenuItem {
            text: qsTr("迷你模式")
            icon.name: "ic_fluent_dock_row_20_regular"
            visible: compact.windowMode !== "mini"
            onTriggered: compact.setWindowMode("mini")
        }
        MenuItem {
            text: qsTr("悬浮球模式")
            icon.name: "ic_fluent_record_20_regular"
            visible: compact.windowMode !== "floating"
            onTriggered: compact.setWindowMode("floating")
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("打开设置")
            icon.name: "ic_fluent_settings_20_regular"
            onTriggered: compact.openMain("settings")
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("重启")
            icon.name: "ic_fluent_arrow_sync_20_regular"
            onTriggered: ConfigManager.restartApplication()
        }
        MenuItem {
            text: qsTr("提权重启")
            icon.name: "ic_fluent_shield_20_regular"
            onTriggered: ConfigManager.restartAsAdmin()
        }
        MenuSeparator {}
        MenuItem {
            // 恢复模式是独立进程：点了就重启过去，不再和当前进程共存。
            text: qsTr("恢复模式")
            icon.name: "ic_fluent_wrench_screwdriver_20_regular"
            onTriggered: ConfigManager.restartWithMode("recovery")
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
            onTriggered: compact.askQuit()
        }
    }

    // 右键那一刻的场景坐标，供菜单定位。
    property point pendingPoint: Qt.point(0, 0)

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
        }

        // 强调色 / 整份配置变化：每个窗口是独立 QML 引擎，都要各自更新。
        function onAccentColorChanged() { compact.applyAccentColor() }
        function onConfigChanged() { compact.applyAccentColor() }

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
        usbDevices = ConfigManager.getRemovableDevices()
    }

    // 老数组和新数组的「可显示信息」一致时就不重建格子，避免每 2.5 秒闪烁。
    function slotSignature(slots) {
        return slots.map(function (slot) {
            return [slot.kind, slot.name, slot.path, slot.icon,
                    slot.enabled === false ? 0 : 1,
                    slot.available === false ? 0 : 1].join("|")
        }).sort().join("\n")
    }

    function refreshLive() {
        storage = ConfigManager.refreshStorageInfo()
        var slots = ConfigManager.getLauncherSlots()
        if (slotSignature(slots) !== slotSignature(panelSlots.concat(storageSlots))) {
            panelSlots = filterRow(slots, 0)
            storageSlots = filterRow(slots, 1)
        }
        usbDevices = ConfigManager.getRemovableDevices()
    }

    // 退出 / 提权两类确认都是屏幕正中的独立置顶窗口，小窗里不留遮罩。
    ConfirmDialog {
        id: quitConfirmDialog
    }

    ConfirmDialog {
        id: adminConfirmDialog
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

    function runSlotAsAdmin(slot) {
        if (!slot || slot.kind !== "action") {
            return
        }
        // 把解析出来的完整动作字段带过去（类型 / 目标 / 参数 / 工作目录 / 按键
        // 序列），缺了会执行出不一样的结果。
        // 右键点名要的提权：带 _explicit_admin 标记，不受「提权前确认 / 自动提权」拦截。
        var payload = {
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

    function slotDetail(slot) {
        if (!slot) return ""
        if (slot.kind === "usb") {
            if (slot.exists === false) return qsTr("没有检测到")
            return qsTr("共 %1 · 剩余 %2")
                .arg(slot.total || "?").arg(slot.free || "?")
        }
        if (slot.kind === "path" && slot.pathType === "file") {
            return slot.exists === false ? qsTr("文件不可用") : String(slot.path || "")
        }
        return slot.exists === false ? qsTr("路径不可用") : String(slot.path || "")
    }

    // 小窗是独立的 QML 根，够不到完整窗口，跨窗口的请求统一走信号交给 Python。
    function openMain(page) {
        compact.openMainRequested(page)
    }

    function popupMoreMenu(anchor) {
        // 菜单右缘贴按钮右缘，向下弹；position 必须是 None，否则 RinUI 的
        // Menu 会按锚点重算 posX/posY，覆盖掉 popup() 指定的坐标。
        var item = anchor || moreButton
        var scene = item.mapToItem(null, item.width, item.height + 4)
        var local = compact.contentItem.mapFromItem(null, scene.x, scene.y)
        var menuWidth = moreMenu.width > 0 ? moreMenu.width : moreMenu.implicitWidth
        moreMenu.popup(Qt.point(Math.max(0, local.x - menuWidth), local.y))
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
