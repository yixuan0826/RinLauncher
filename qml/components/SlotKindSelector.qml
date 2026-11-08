import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 槽位类型选择：说明文字 + 一排可选卡片。
//
// 类型只有三种，用卡片比下拉框直观 —— 卡片上直接带一句 hint，不用点开才知道
// 每种类型是干什么的。选中态用主色边框 + 淡底 + 加粗文字表达，图标保持单色。
ColumnLayout {
    id: root

    // 当前的种类名（action / tool / path 之一）。
    property string current: "action"
    // 每项：{ kind, title, icon, hint }
    property var options: []

    signal picked(string kind)

    readonly property var activeOption: {
        for (var i = 0; i < root.options.length; ++i) {
            if (root.options[i].kind === root.current) {
                return root.options[i]
            }
        }
        return ({})
    }

    Layout.fillWidth: true
    // 与外层表单的 12 保持一致：标题组和卡片组之间留正常间距。
    spacing: 12

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 1

        Text {
            Layout.fillWidth: true
            typography: Typography.BodyStrong
            color: Theme.currentTheme.colors.textColor
            text: qsTr("这一格用来做什么？")
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: root.activeOption.hint || ""
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Repeater {
            model: root.options

            delegate: Frame {
                id: kindTile

                readonly property bool selected: root.current === modelData.kind

                Layout.fillWidth: true
                Layout.preferredHeight: 58
                padding: 0
                radius: Theme.currentTheme.appearance.windowRadius
                border.color: selected
                    ? Theme.currentTheme.colors.primaryColor
                    : Theme.currentTheme.colors.cardBorderColor
                color: selected
                    ? Qt.rgba(Theme.currentTheme.colors.primaryColor.r,
                              Theme.currentTheme.colors.primaryColor.g,
                              Theme.currentTheme.colors.primaryColor.b, 0.16)
                    : (kindMouse.containsMouse
                        ? Theme.currentTheme.colors.subtleSecondaryColor
                        : Theme.currentTheme.colors.cardColor)

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    spacing: 8

                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        iconKey: modelData.icon
                        iconSize: 18
                        tint: Theme.currentTheme.colors.textColor
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        typography: Typography.Caption
                        font.bold: kindTile.selected
                        color: kindTile.selected
                            ? Theme.currentTheme.colors.primaryColor
                            : Theme.currentTheme.colors.textColor
                        text: modelData.title
                    }
                }

                MouseArea {
                    id: kindMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(modelData.kind)
                }

                ToolTip.text: modelData.hint
                ToolTip.visible: kindMouse.containsMouse
                ToolTip.delay: 500
            }
        }
    }
}
