import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI

// 小窗的两个面板行：最多 10 格，排成 2 × 5（6 格时 3 + 3）。
//
// 排版规则沿用 1.1.6：
//   * ≤ 5 格：一行铺满；
//   * 6–10 格：两行平分，避免「5 + 1」那种一头沉。
//
// 1.1.7 引入的三档尺寸（小 / 中 / 大）只决定**格子边长上限**，不再改变每行格数：
// 实际边长 = min(档位目标, 按列数算出来的可用宽度)，所以永远不越界。
Item {
    id: panel

    property var slots: []
    // 最多显示的格数（配置里多出来的上不了小窗，由设置页提醒）。
    property int capacity: 10
    // 全局三档：small / medium / large。
    property string sizeMode: "medium"
    // Fluent 2 的 8px 间距节奏：行之间、格子之间都取 8。
    property int gap: 8

    signal activated(var slot)
    signal menuRequested(var slot, real sceneX, real sceneY)

    readonly property int shownCount: Math.min(slots.length, capacity)
    // 一行最多 5 格：6 格以上按两行平分，10 格正好 5 + 5。
    readonly property int perLine: shownCount === 0 ? 0
        : shownCount <= 5 ? shownCount : Math.ceil(shownCount / 2)
    readonly property int rows: shownCount === 0 ? 0
        : Math.ceil(shownCount / perLine)
    // 档位对应的目标边长；「中」= 76 与 1.1.6 的默认观感一致。
    readonly property real targetTile: sizeMode === "small" ? 56
                                     : sizeMode === "large" ? 88 : 76
    readonly property real tileSize: shownCount === 0 ? 0
        : Math.max(36, Math.min(targetTile,
                                Math.floor((width - (perLine - 1) * gap) / perLine)))

    // 第 rowIndex 行的槽位。
    //
    // 不用「把分行结果存成数组再交给 Repeater 当 model」：模型随宽度变化重建时
    // 会在 Qt 的列布局里踩到 use-after-free（真机上直接 access violation）。
    // 这里改成固定 capacity 个行委托，每行自己去取切片，模型永不重建。
    function lineAt(rowIndex) {
        if (rowIndex < 0 || rowIndex >= rows) {
            return []
        }
        var start = rowIndex * perLine
        return slots.slice(start, Math.min(shownCount, start + perLine))
    }

    Column {
        anchors.centerIn: parent
        width: parent.width
        spacing: panel.gap

        Repeater {
            model: panel.capacity

            delegate: CompactRow {
                required property int index

                visible: index < panel.rows
                width: parent.width
                height: panel.tileSize
                slots: panel.lineAt(index)
                style: "big"
                tileSizeOverride: panel.tileSize
                onActivated: panel.activated(slot)
                onMenuRequested: panel.menuRequested(slot, sceneX, sceneY)
            }
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
