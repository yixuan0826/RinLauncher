import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI
import QtQuick.Window 2.15

import "../components"

// 小窗专用菜单：独立置顶窗口，定位与尺寸完全自己算。
//
// 为什么不用 QQC2 的 Menu（哪怕 popupType: Window）：启动台是置底、不抢焦点的
// 桌面挂件，Menu 在它上面 open 之后会被 Qt 立刻关掉，x/y 也会被重置成 0 ——
// 表现就是菜单闪一下就没了、或者整块跑到屏幕外。
//
// items 每项：{ icon, text, action, enabled, danger, separator }
Window {
    id: menuWindow

    objectName: "compactMenuWindow"

    property var items: []
    property rect screenArea: Qt.rect(0, 0, 0, 0)

    readonly property int itemHeight: 34
    readonly property int menuWidth: 208
    // 独立顶层窗口没有 RinUI 的窗口材质兜底。主题切换 / 首帧未就绪时，
    // Theme 里可能取到 null 或无效颜色，窗口会整块透明、只剩文字浮在桌面上。
    // 这里统一兜底成不透明底色，并校验主题色本身确实不透明。
    readonly property color surfaceColor: {
        try {
            var theme = Theme.currentTheme
            if (theme && theme.colors && theme.colors.backgroundColor) {
                var value = theme.colors.backgroundColor
                if (value.a !== undefined && value.a >= 0.99) {
                    return value
                }
            }
        } catch (error) {
            // 主题对象尚未创建 / 已销毁，走下面的固定色。
        }
        return "#202020"
    }
    readonly property color borderColor: {
        try {
            var theme = Theme.currentTheme
            if (theme && theme.colors && theme.colors.windowBorderColor) {
                return theme.colors.windowBorderColor
            }
        } catch (error) {
            // 同上。
        }
        return "#4a4a4a"
    }
    readonly property int surfaceRadius: {
        try {
            var theme = Theme.currentTheme
            if (theme && theme.appearance
                    && theme.appearance.windowRadius !== undefined) {
                return theme.appearance.windowRadius
            }
        } catch (error) {
            // 同上。
        }
        return 8
    }

    width: menuWidth
    // 高度直接按数据算：依赖 Column.implicitHeight 的话，items 赋值的那一帧
    // 布局还没算完，height 还是旧值，夹紧计算会直接把菜单压到屏幕外。
    height: measure(items)
    visible: false
    // 不透明窗口底色：即使 QML 背景矩形因为主题切换丢了一帧，窗口也不会
    // 变成整块透明。圆角由 Win10 的窗口 region / Win11 的 DWM 负责裁。
    color: surfaceColor
    flags: Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

    function measure(list) {
        var total = 8
        var count = list ? list.length : 0
        for (var i = 0; i < count; ++i) {
            total += list[i].separator ? 9 : itemHeight
        }
        return total
    }

    // 屏幕坐标；优先放在锚点上方，放不下翻到下方，再按可用区域夹紧。
    function openAt(screenX, screenY, list, area) {
        closeMenu()
        items = list
        screenArea = area
        var minX = area.x + 4
        var minY = area.y + 4
        var maxX = area.x + area.width - width - 4
        var maxY = area.y + area.height - height - 4
        var xPos = screenX - width
        var yPos = screenY - height - 4
        if (yPos < minY) {
            yPos = screenY + 4
        }
        x = Math.min(Math.max(xPos, minX), Math.max(minX, maxX))
        y = Math.min(Math.max(yPos, minY), Math.max(minY, maxY))
        show()
        requestActivate()
        raise()
    }

    // 右键菜单：贴着鼠标出现，空间不够时向左 / 向上翻，不允许跑到屏幕外。
    function openAtCursor(screenX, screenY, list, area) {
        closeMenu()
        items = list
        screenArea = area
        var minX = area.x + 4
        var minY = area.y + 4
        var maxX = area.x + area.width - width - 4
        var maxY = area.y + area.height - height - 4
        var xPos = screenX + 2
        var yPos = screenY + 2
        if (xPos > maxX) {
            xPos = screenX - width - 2
        }
        if (yPos > maxY) {
            yPos = screenY - height - 2
        }
        x = Math.min(Math.max(xPos, minX), Math.max(minX, maxX))
        y = Math.min(Math.max(yPos, minY), Math.max(minY, maxY))
        show()
        requestActivate()
        raise()
    }

    function closeMenu() {
        visible = false
        // 菜单项里存着捕获 slot 的 JS 闭包；关掉后清空，避免长期持有配置对象。
        items = []
    }

    function activate(index) {
        var item = items[index]
        closeMenu()
        if (item && item.action) {
            item.action()
        }
    }

    // 窗口失焦（点别处）就收起。
    onActiveChanged: {
        if (!active) {
            closeMenu()
        }
    }

    Shortcut {
        sequences: ["Escape"]
        onActivated: menuWindow.closeMenu()
    }

    Rectangle {
        anchors.fill: parent
        radius: menuWindow.surfaceRadius
        color: menuWindow.surfaceColor
        border.width: 1
        border.color: menuWindow.borderColor
    }

    Column {
        id: contentColumn

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 4
        spacing: 0

        Repeater {
            model: menuWindow.items

            delegate: Item {
                id: rowItem

                required property int index
                required property var modelData

                width: contentColumn.width
                height: modelData.separator ? 9 : menuWindow.itemHeight

                Rectangle {
                    visible: !rowItem.modelData.separator
                    anchors.fill: parent
                    radius: 4
                    color: rowMouse.containsMouse
                        ? Theme.currentTheme.colors.subtleSecondaryColor
                        : "transparent"
                }

                Rectangle {
                    visible: rowItem.modelData.separator === true
                    x: 8
                    width: parent.width - 16
                    height: 1
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.currentTheme.colors.dividerBorderColor
                }

                Row {
                    visible: !rowItem.modelData.separator
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    AppIcon {
                        width: 16
                        height: 16
                        iconKey: rowItem.modelData.icon || ""
                        iconSize: 16
                        tint: rowItem.modelData.enabled === false
                            ? Theme.currentTheme.colors.textSecondaryColor
                            : (rowItem.modelData.danger
                               ? Theme.currentTheme.colors.systemCriticalColor
                               : Theme.currentTheme.colors.textColor)
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        font.pixelSize: Theme.currentTheme.typography.bodySize
                        color: rowItem.modelData.enabled === false
                            ? Theme.currentTheme.colors.textSecondaryColor
                            : (rowItem.modelData.danger
                               ? Theme.currentTheme.colors.systemCriticalColor
                               : Theme.currentTheme.colors.textColor)
                        text: rowItem.modelData.text || ""
                    }
                }

                MouseArea {
                    id: rowMouse

                    anchors.fill: parent
                    hoverEnabled: !rowItem.modelData.separator
                    enabled: !rowItem.modelData.separator
                        && rowItem.modelData.enabled !== false
                    cursorShape: Qt.PointingHandCursor
                    onClicked: menuWindow.activate(rowItem.index)
                }
            }
        }
    }
}
