import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 图标网格：一行铺满、自动算列数，选中态是一圈描边而不是「点一下就没了」。
//
// 从图标选择器里抽出来，是因为「我的图标」与内置/随包列表只差一个删除按钮，
// 同一份委托写三遍很容易改歪一处。
//
// 必须是 GridView（不是 ListView）：ListView 只会沿一个方向排，光改委托的
// width 是不会换行的。
GridView {
    id: grid

    property var icons: []
    property int cellSize: 52
    property string selectedKey: ""
    property color tint: Theme.currentTheme.colors.textColor
    // 打开后每格右上角会多一个删除按钮（只对用户自己的图标有意义）。
    property bool deletable: false

    signal picked(string iconKey)
    signal removeRequested(string iconKey)

    clip: true
    model: icons
    // 列数按可用宽度算，格子本身由 cellWidth 均分铺满。
    readonly property int columns: Math.max(1, Math.floor(width / (cellSize + 12)))
    cellWidth: width / columns
    cellHeight: cellSize + 10

    delegate: Item {
        id: cell

        readonly property bool selected: grid.selectedKey === modelData

        width: grid.cellWidth
        height: grid.cellHeight

        Rectangle {
            id: plate
            anchors.centerIn: parent
            width: grid.cellSize
            height: grid.cellSize
            radius: Theme.currentTheme.appearance.windowRadius
            color: cell.selected
                ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                          Theme.currentTheme.colors.primaryColor.g,
                          Theme.currentTheme.colors.primaryColor.b, 0.12)
                : pointer.containsMouse
                    ? Theme.currentTheme.colors.subtleSecondaryColor
                    : "transparent"
            border.width: cell.selected || pointer.containsMouse ? 1 : 0
            border.color: cell.selected
                ? Theme.currentTheme.colors.primaryColor
                : Theme.currentTheme.colors.cardBorderColor
        }

        AppIcon {
            anchors.centerIn: parent
            iconKey: modelData
            iconSize: Math.round(grid.cellSize * 0.5)
            tint: grid.tint
        }

        MouseArea {
            id: pointer
            anchors.fill: plate
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            onClicked: grid.picked(modelData)
        }

        ToolButton {
            anchors.right: plate.right
            anchors.top: plate.top
            anchors.margins: -8
            width: 22
            height: 22
            visible: grid.deletable && (pointer.containsMouse || cell.selected)
            icon.name: "ic_fluent_dismiss_20_regular"
            ToolTip.text: qsTr("从图标库删除")
            onClicked: grid.removeRequested(modelData)
        }
    }
}
