import QtQuick 2.15
import QtQuick.Layouts 2.15
import RinUI

// 区块标题：一个图标 + 主标题 + 右侧补充说明。
//
// 启动台的三段（软件区 / 工具区 / 简易设置）共用它，保证分区节奏一致。
RowLayout {
    id: header

    property string iconKey: ""
    property string title: ""

    Layout.fillWidth: true
    spacing: 8

    AppIcon {
        Layout.alignment: Qt.AlignVCenter
        iconKey: header.iconKey
        iconSize: 18
        // 分区图标不再上强调色：全部图标保持单色，交给标题文字做重心。
        tint: Theme.currentTheme.colors.textColor
    }

    Text {
        Layout.alignment: Qt.AlignVCenter
        typography: Typography.BodyStrong
        color: Theme.currentTheme.colors.textColor
        text: header.title
    }

    Item { Layout.fillWidth: true }
}
