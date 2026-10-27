import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI

// 小窗的面板：把槽位按「每行能放几格」自动排成若干行（最多 10 格）。
//
// 尺寸不再按「固定两行平分」，而是由全局档位（小 / 中 / 大）给出一个目标边长，
// 再看面板宽度决定一行放几格、总共几行：
//   * 档位只影响目标边长（56 / 76 / 88），不写死每行格数；
//   * 实际边长会被宽度反推压小，保证永远不越界；
//   * 每行塞满能放下的格数，最后一行自然短一截也居中。
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
    // 档位对应的目标边长；与设置页的「小 / 中 / 大」一一对应。
    // 「中」= 76，与 1.1.6 的默认观感一致，升级后不会突然变小。
    readonly property real targetTile: sizeMode === "small" ? 56
                                     : sizeMode === "large" ? 88 : 76
    // 宽度够放几格（至少 1 格）。
    readonly property int fitPerLine: Math.max(
        1, Math.floor((width + gap) / (targetTile + gap)))
    readonly property int rows: shownCount === 0 ? 0
        : Math.ceil(shownCount / fitPerLine)
    // 每行直接塞满：最后一行的零头居中显示，不为了「平均」把前面的行也拆小。
    readonly property int perLine: rows === 0 ? 0 : fitPerLine
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
