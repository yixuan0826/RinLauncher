import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI

// 小窗里的一格：图标在上、单行标题在下。
//
// 被 CompactRow 用来画前两行 —— 大格子放应用，小格子放功能。两种形态只是尺寸
// 不同，所以用 style 切换而不是拆成两个组件。
Item {
    id: tile

    property var slot: null
    property string style: "big"        // big = 应用大格，mini = 功能小格

    signal activated(var slot)
    signal menuRequested(var slot, real sceneX, real sceneY)

    readonly property bool mini: style === "mini"
    readonly property bool empty: !slot
    // 引用了被停用的条目时，Python 那边就不会把这一格解析出来，所以这里只兜底。
    readonly property bool disabled: slot ? slot.enabled === false : false
    // 小格子只有 50px 上下，字号得再收一点，否则「启动台设置」这种五字标题
    // 会折成 4+1 两行，第二行孤零零一个字很难看。
    readonly property int labelSize: mini ? 9 : 11
    // 标题最多两行。行高必须按像素给：RinUI 的 Text 是 FixedHeight 语义的
    // lineHeight，以前写 0.95 实际就是「两行只隔 0.95 像素」，字全叠在一起。
    readonly property int labelLineHeight: labelSize + 4
    readonly property int labelBlock: labelLineHeight * 2
    // 图标给两行标题让位：剩下的空间里取大（但不超过原来的比例），至少 14。
    readonly property real iconSize: Math.max(14, Math.min(
        mini ? 22 : Math.round(width * 0.36),
        height - labelBlock - (mini ? 3 : 5) - 8))

    width: mini ? 56 : 76
    height: mini ? 58 : width
    opacity: empty ? 0.3 : disabled ? 0.45 : 1

    // 按下去时整格缩一点，「按到了」有个即时反馈；时长跟着动画总开关走。
    scale: pointer.pressed && !tile.empty ? 0.93 : 1
    Behavior on scale {
        NumberAnimation { duration: Utils.animationSpeedFaster; easing.type: Easing.OutCubic }
    }

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: pointer.pressed || pointer.hovered
            ? Theme.currentTheme.colors.controlSecondaryColor
            : "transparent"
        border.width: pointer.hovered || tile.empty ? 1 : 0
        border.color: tile.empty
            ? Theme.currentTheme.colors.cardBorderColor
            : Theme.currentTheme.colors.primaryColor

        Behavior on color {
            ColorAnimation { duration: Utils.animationSpeedFaster; easing.type: Easing.OutCubic }
        }
    }

    Column {
        anchors.centerIn: parent
        width: parent.width - 6
        spacing: tile.mini ? 3 : 5

        AppIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            iconKey: tile.slot ? tile.slot.icon : ""
            iconSize: tile.iconSize
            placeholder: "ic_fluent_add_20_regular"
            tint: tile.empty || tile.disabled
                ? Theme.currentTheme.colors.textSecondaryColor
                : Theme.currentTheme.colors.primaryColor
        }

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            // 每格只有 50~76px，标题四五个字就装不下，允许折成两行，
            // 免得变成「打开配置…」这种读不出意思的省略号。长单词 / 网址
            // 没有空格可断，用 WrapAtWordBoundaryOrAnywhere 兜住。
            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeightMode: Text.FixedHeight
            lineHeight: tile.labelLineHeight
            font.pixelSize: tile.labelSize
            color: Theme.currentTheme.colors.textColor
            text: tile.slot ? tile.slot.name : ""
        }
    }

    // 提权条目给个小盾牌角标，和完整窗口里的语义对齐。
    AppIcon {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 2
        visible: !!tile.slot && tile.slot.admin === true
        iconKey: "ic_fluent_shield_20_regular"
        iconSize: 11
        tint: Theme.currentTheme.colors.primaryColor
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton

        onReleased: {
            if (mouse.button === Qt.LeftButton && containsMouse && !tile.empty) {
                tile.activated(tile.slot)
            }
        }
        onClicked: {
            if (mouse.button === Qt.RightButton) {
                // 映射到场景坐标，菜单才能在任何父级里正确定位。
                var scene = tile.mapToItem(null, mouseX, mouseY)
                tile.menuRequested(tile.slot, scene.x, scene.y)
            }
        }
    }
}
