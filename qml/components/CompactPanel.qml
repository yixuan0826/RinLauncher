import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI

// 小窗的双行面板：把槽位平分到上下两排（最多 10 格），两排共用同一个格子尺寸。
//
// 平分而不是「前排塞满 5 个」是因为 6 格时 5+1 看着很散；3+3 更稳，空格子也
// 不会跑出来。尺寸按列数最多的那排算，所以两排的格子一样大。
Item {
    id: panel

    property var slots: []
    // 最多显示的格数（配置里多出来的上不了小窗，由设置页提醒）。
    property int capacity: 10
    // Fluent 2 的 8px 间距节奏：两排之间、格子之间都取 8。
    property int gap: 8

    signal activated(var slot)
    signal menuRequested(var slot, real sceneX, real sceneY)

    readonly property int shownCount: Math.min(slots.length, capacity)
    readonly property int perLine: shownCount <= 5
        ? Math.max(shownCount, 1)
        : Math.ceil(shownCount / 2)
    readonly property real tileSize: shownCount === 0 ? 0
        : Math.max(44, Math.min(76,
                                Math.floor((width - (perLine - 1) * gap) / perLine)))
    readonly property var line1: slots.slice(0, perLine)
    readonly property var line2: slots.slice(perLine, perLine * 2)

    Column {
        anchors.centerIn: parent
        width: parent.width
        spacing: panel.gap

        CompactRow {
            width: parent.width
            height: panel.tileSize
            slots: panel.line1
            style: "big"
            tileSizeOverride: panel.tileSize
            onActivated: panel.activated(slot)
            onMenuRequested: panel.menuRequested(slot, sceneX, sceneY)
        }

        CompactRow {
            width: parent.width
            height: panel.tileSize
            visible: panel.line2.length > 0
            slots: panel.line2
            style: "big"
            tileSizeOverride: panel.tileSize
            onActivated: panel.activated(slot)
            onMenuRequested: panel.menuRequested(slot, sceneX, sceneY)
        }
    }

    // 面板空了也要占着这块地，留一句话免得看上去像坏了。
    Text {
        anchors.centerIn: parent
        visible: panel.slots.length === 0
        typography: Typography.Caption
        color: Theme.currentTheme.colors.textSecondaryColor
        text: qsTr("面板还是空的，去启动台页加几格")
    }
}
