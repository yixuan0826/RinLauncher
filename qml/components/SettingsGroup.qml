import QtQuick 2.15
import QtQuick.Layouts 2.15
import RinUI

// 设置分组：一个小标题 + 一张承载若干 FormRow 的卡片。
ColumnLayout {
    id: group

    property string title: ""
    property string iconKey: ""

    default property alias content: inner.data

    Layout.fillWidth: true
    spacing: 12

    ZoneHeader {
        Layout.fillWidth: true
        iconKey: group.iconKey
        title: group.title
    }

    Frame {
        Layout.fillWidth: true
        padding: 16
        radius: Theme.currentTheme.appearance.windowRadius

        ColumnLayout {
            id: inner
            anchors.fill: parent
            spacing: 12
        }
    }
}
