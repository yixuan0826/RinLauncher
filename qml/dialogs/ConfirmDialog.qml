import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI
// 同 CompactWindow：QtQuick.Window 放最后导入，确保 Window 解析成 Qt 的顶层窗口，
// 而不是 RinUI 那套自带标题栏与背景的窗口包装。
import QtQuick.Window 2.15

// 确认弹窗：独立顶层窗口，屏幕居中 + 置顶。
//
// 1.1.12 起不再用「页面内遮罩 + 卡片」：启动台是不接受焦点的置底桌面挂件，
// 内嵌遮罩既盖不住别的窗口，也拿不到键盘焦点。改成独立窗口后，无论从哪个
// 窗口弹出，都出现在屏幕正中，能直接回车确认 / Esc 取消。用法不变：
//
//     confirmDialog.ask("确定要删除吗？", function() { ... })
Window {
    id: confirmDialog
    objectName: "confirmDialogWindow"

    property string message: ""
    property string confirmText: qsTr("动手！")
    property string cancelText: qsTr("先别……")
    property var callback: null

    readonly property int cardWidth: 420
    // 内容多高窗口就多高，不用给死高度，也不裁字。
    readonly property int cardHeight: Math.max(132, content.implicitHeight + 48)

    width: cardWidth
    height: cardHeight
    visible: false
    color: "transparent"
    title: qsTr("确认")
    // 独立窗口 + 无边框 + 置顶；不指定 transientParent：启动台是置底窗口，
    // 任何父子关系都会把这个弹窗一起压到底层（实测弹窗直接跑到桌面后面）。
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    transientParent: null

    function centerOnScreen() {
        var sw = Screen.desktopAvailableWidth > 0
            ? Screen.desktopAvailableWidth : Screen.width
        var sh = Screen.desktopAvailableHeight > 0
            ? Screen.desktopAvailableHeight : Screen.height
        x = Math.round(Screen.virtualX + (sw - width) / 2)
        y = Math.round(Screen.virtualY + (sh - height) / 2)
    }

    function open() {
        centerOnScreen()
        show()
        raise()
        requestActivate()
    }

    function close() {
        hide()
    }

    function accept() {
        hide()
        if (callback) {
            callback()
        }
    }

    function reject() {
        hide()
    }

    function ask(text, action, options) {
        message = text
        callback = action
        confirmText = (options && options.confirmText) || qsTr("动手！")
        cancelText = (options && options.cancelText) || qsTr("先别……")
        open()
    }

    // 独立窗口自己收键盘：回车确认、Esc 取消。
    Shortcut {
        sequences: ["Return", "Enter"]
        onActivated: confirmDialog.accept()
    }
    Shortcut {
        sequences: ["Escape"]
        onActivated: confirmDialog.reject()
    }

    // 卡片铺满窗口：圆角与描边都画在这里，窗口本身全透明。
    Rectangle {
        anchors.fill: parent
        radius: Theme.currentTheme.appearance.windowRadius
        color: Theme.currentTheme.colors.backgroundColor
        border.width: 1
        border.color: Theme.currentTheme.colors.windowBorderColor

        // 吃掉落在卡片上的点击，别穿透到底下的窗口。
        MouseArea {
            anchors.fill: parent
        }
    }

    Column {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        spacing: 14

        Text {
            width: parent.width
            elide: Text.ElideRight
            color: Theme.currentTheme.colors.textColor
            font.pixelSize: Theme.currentTheme.typography.bodyStrongSize + 2
            font.weight: Font.DemiBold
            text: qsTr("确认")
        }

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.textColor
            font.pixelSize: Theme.currentTheme.typography.bodySize
            text: confirmDialog.message
        }

        Row {
            width: parent.width
            spacing: 8
            // 主按钮在右侧，和 Fluent 的确认框一致。
            layoutDirection: Qt.RightToLeft

            Button {
                text: confirmDialog.confirmText
                highlighted: true
                onClicked: confirmDialog.accept()
            }

            Button {
                text: confirmDialog.cancelText
                onClicked: confirmDialog.reject()
            }
        }
    }
}
