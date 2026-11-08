import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 槽位编辑器的预览卡：图标 + 显示名 + 一行说明。
// 从 SlotEditorDialog.qml 拆出来，那支文件只留表单骨架与提交逻辑。
Frame {
    id: root

    property string iconKey: ""
    property string previewTitle: ""
    property string previewDetail: ""

    Layout.fillWidth: true
    Layout.preferredHeight: 92

    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14

        AppIcon {
            Layout.alignment: Qt.AlignVCenter
            iconKey: root.iconKey
            iconSize: 40
            tint: Theme.currentTheme.colors.textColor
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2

            Text {
                Layout.fillWidth: true
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                font.bold: true
                color: Theme.currentTheme.colors.textColor
                text: root.previewTitle
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.NoWrap
                elide: Text.ElideMiddle
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: root.previewDetail
            }
        }
    }
}
