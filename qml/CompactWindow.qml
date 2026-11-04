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
    // 两种形态各用各的圆角：完整窗口跟系统令牌，迷你条做成胶囊。
    readonly property int surfaceRadius: miniMode
        ? Math.round(height / 2) : cardRadius

    // ── 形态 ──
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

        // 简易 toast：常驻小窗没有 FloatLayer 那种容器，自绘一条更合适。
        Rectangle {
            id: toast

            anchors.horizontalCenter: card.horizontalCenter
            anchors.bottom: card.bottom
            // 完整模式给底部系统控制条留位置；迷你条贴着卡片底部即可。
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

    // 菜单内容一律走独立窗口；屏幕坐标 = 窗口坐标 + 场景坐标。
    function popupMoreMenu(anchor) {
        var item = anchor || (miniMode ? miniMoreButton : moreButton)
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

    // 菜单内容项的真实尺寸：Popup 自己的 width/height 在打开后仍然可能是 0，
    // 拿它算位置就会把菜单甩到屏幕外（"右对齐"不左移、"向上"不上升）。
    function menuMetrics(menu) {
        var width = menu.width
        var height = menu.height
        // contentItem 的 implicit 尺寸不含菜单内边距，只能当兜底。
        var item = menu.contentItem
        if (item) {
            if (!(width > 0)) {
                width = item.implicitWidth
            }
            if (!(height > 0)) {
                height = item.implicitHeight
            }
        }
        if (!(width > 0)) {
            width = menu.implicitWidth
        }
        if (!(height > 0)) {
            height = menu.implicitHeight
        }
        return Qt.point(width, height)
    }

    // 把菜单摆到屏幕可用区域内：先在关闭状态算好坐标再 open。
    // 菜单未打开时 implicitWidth / implicitHeight 已经是最终尺寸；open 之后
    // 再改 x/y 会让 Qt 重新定位（甚至直接关掉菜单），所以只设一次。
    function popupMenuAt(menu, sceneX, sceneY, alignRight, preferUp) {
        var metrics = menuMetrics(menu)
        var menuWidth = metrics.x
        var menuHeight = metrics.y
        var screenX = compact.x + sceneX
        var screenY = compact.y + sceneY
        var minX = (primaryWidth > 0 ? primaryX : Screen.virtualX) + 4
        var minY = (primaryHeight > 0 ? primaryY : Screen.virtualY) + 4
        var areaWidth = primaryWidth > 0 ? primaryWidth : Screen.desktopAvailableWidth
        var areaHeight = primaryHeight > 0 ? primaryHeight : Screen.desktopAvailableHeight
        var x = alignRight ? screenX - menuWidth : screenX
        var y = preferUp ? screenY - menuHeight : screenY
        // 翻转：上方放不下就向下；下方放不下就向上。
        if (y < minY && screenY + menuHeight <= minY + areaHeight) {
            y = screenY
        }
        if (y + menuHeight > minY + areaHeight && screenY - menuHeight >= minY) {
            y = screenY - menuHeight
        }
        x = Math.min(Math.max(x, minX), Math.max(minX, minX + areaWidth - menuWidth))
        y = Math.min(Math.max(y, minY), Math.max(minY, minY + areaHeight - menuHeight))
        // Popup 的 x/y 是相对父窗口的坐标。
        menu.x = x - compact.x
        menu.y = y - compact.y
        menu.open()
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
        var list = []
        list.push({
            icon: "ic_fluent_open_20_regular",
            text: slot.kind === "usb" ? qsTr("打开可移动磁盘")
                : slot.kind === "path" ? qsTr("打开这个位置") : qsTr("打开"),
            action: function () { compact.runSlot(slot) }
        })
        if (slot.kind === "action" && (slot.type === "file" || slot.type === "cmd")) {
            list.push({ icon: "ic_fluent_shield_20_regular",
                        text: qsTr("以管理员身份打开"),
                        action: function () { compact.runSlotAsAdmin(slot) } })
        }
        // 存储行两张卡片是钉死的（路径在设置页改），只有面板格子有编辑入口。
        if (slot.row === 0) {
            list.push({ separator: true })
            list.push({ icon: "ic_fluent_edit_20_regular", text: qsTr("编辑这一格…"),
                        action: function () { compact.editSlot(slot) } })
            list.push({ icon: "ic_fluent_add_20_regular", text: qsTr("再加一格…"),
                        action: function () { compact.addSlotToRow(slot) } })
        }
        compactMenu.openAt(compact.x + sceneX, compact.y + sceneY, list, menuArea())
    }
}
