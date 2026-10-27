import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 统一的确认提示框。
//
// 取代早期用 `Qt.createQmlObject()` 现场拼出来的对话框 —— 那样每次调用都会在
// 运行期重新解析一遍 QML，并且泄漏一个对象。用法：
//
//     confirmDialog.ask("确定要删除吗？", function() { ... })
AppDialog {
    id: confirmDialog

    property string message: ""
    property string confirmText: qsTr("动手！")
    property string cancelText: qsTr("先别……")
    property var callback: null

    title: qsTr("确认")
    preferredWidth: 420

    function ask(text, action, options) {
        message = text
        callback = action
        confirmText = (options && options.confirmText) || qsTr("动手！")
        open()
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 12

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.textColor
            text: confirmDialog.message
        }
    }

    footer: RowLayout {
        spacing: 8

        Item { Layout.fillWidth: true }

        Button {
            text: confirmDialog.cancelText
            onClicked: confirmDialog.reject()
        }

        Button {
            text: confirmDialog.confirmText
            highlighted: true
            onClicked: {
                confirmDialog.accept()
                if (confirmDialog.callback) {
                    confirmDialog.callback()
                }
            }
        }
    }
}
