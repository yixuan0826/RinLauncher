import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 槽位的「内置功能」与「固定位置」两组字段。
//
// 动作类槽位（kind === "action"）的字段全部由 ActionForm 自己管，不在这里。
// 拆出来是为了让 SlotEditorDialog 只剩表单骨架和提交逻辑；这几个 FormRow
// 原来是文件里最长的一段纯排版代码。
ColumnLayout {
    id: root

    // 只有 kind === "tool" / "path" 时对应行才可见。
    property string kind: "action"

    // 内置功能
    property string toolKey: ""
    property var toolNames: []
    property var toolKeys: []

    // 固定位置
    property string pathType: "disk"
    property string path: ""
    property var drives: []

    readonly property var driveLabels: root.drives.map(function (item) {
        return item.total.length > 0
            ? "%1（%2，剩余 %3）".arg(item.label).arg(item.kindLabel).arg(item.free)
            : "%1（%2）".arg(item.label).arg(item.kindLabel)
    })

    Layout.fillWidth: true
    spacing: 12

    // ── 内置功能 ──
    FormRow {
        visible: root.kind === "tool"
        label: qsTr("功能")
        description: qsTr("小窗自带的功能")
        RinComboBox {
            Layout.fillWidth: true
            Layout.maximumWidth: 320
            model: root.toolNames
            currentIndex: Math.max(0, root.toolKeys.indexOf(root.toolKey))
            onActivated: function (index) {
                root.toolKey = root.toolKeys[index] || ""
            }
        }
    }

    // ── 固定位置：磁盘 / 文件位置 ──
    FormRow {
        visible: root.kind === "path"
        label: qsTr("位置类型")
        RinComboBox {
            Layout.preferredWidth: 180
            model: [qsTr("磁盘"), qsTr("文件位置")]
            currentIndex: root.pathType === "file" ? 1 : 0
            onActivated: function (index) {
                root.pathType = index === 1 ? "file" : "disk"
            }
        }
    }

    FormRow {
        visible: root.kind === "path" && root.pathType === "disk"
        label: qsTr("磁盘")
        description: qsTr("把卡片固定到某块盘；小窗显示卷标")
        RinComboBox {
            Layout.fillWidth: true
            Layout.maximumWidth: 320
            model: root.driveLabels
            onActivated: function (index) {
                root.path = root.drives[index].path
            }
        }
        ToolButton {
            icon.name: "ic_fluent_folder_open_20_regular"
            ToolTip.text: qsTr("选一个文件夹")
            onClicked: {
                var picked = ConfigManager.pickFolder()
                if (picked.length > 0) {
                    root.path = picked
                    root.pathType = "disk"
                }
            }
        }
    }

    FormRow {
        visible: root.kind === "path" && root.pathType === "file"
        label: qsTr("文件位置")
        description: qsTr("点开时打开所在目录并选中文件")
        TextField {
            Layout.fillWidth: true
            placeholderText: qsTr("例如 C:\\Tools\\notes.txt")
            text: root.path
            onTextChanged: root.path = text
        }
        ToolButton {
            icon.name: "ic_fluent_document_20_regular"
            ToolTip.text: qsTr("选一个文件")
            onClicked: {
                var picked = ConfigManager.pickFile()
                if (picked.length > 0) {
                    root.path = picked
                    root.pathType = "file"
                }
            }
        }
    }
}
