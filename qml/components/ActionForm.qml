import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 动作参数表单：类型 / 目标 / 参数 / 工作目录 / 管理员，以及按键序列编辑器。
//
// 启动台格子编辑器（动作类）用这一份 —— 之前「快捷操作」和槽位两边各写一套
// 字段与校验，改一处漏一处；库那边改只读后只剩这一处消费方。
// 「按键模拟」参考 SystemTools 的「模拟键盘」：编辑器支持全局录制 + 步骤列表 +
// 底部编辑行（操作 / 键码 / 名称 / 延迟），实现见 KeyboardStepsEditor。
// 外部用 load() 灌入初始值、read() 取回一个动作对象。
ColumnLayout {
    id: form

    property string actionType: "file"
    property var steps: []

    readonly property var typeKeys: ["file", "cmd", "url", "keyboard"]

    Layout.fillWidth: true
    spacing: 10

    // ------------------------------------------------------------------
    // 取值
    // ------------------------------------------------------------------
    function load(data) {
        data = data || {}
        actionType = String(data.type || "file")
        if (actionType === "keymouse") {
            actionType = "keyboard"   // 旧配置兼容
        }
        var source = data.keyboard_steps || data.keymouse_steps || []
        // 深拷贝再编辑，取消编辑不会动到配置里的原数组；鼠标步骤直接跳过。
        steps = JSON.parse(JSON.stringify(source)).filter(function (step) {
            return step && (step.type === "key" || step.type === "wait")
        })
        keyboardEditor.resetSelection()
        typeCombo.currentIndex = Math.max(0, typeKeys.indexOf(actionType))
        targetField.text = data.target || ""
        argsField.text = data.arguments || ""
        workdirField.text = data.working_dir || ""
        adminSwitch.checked = data.run_as === "admin"
    }

    function read() {
        return {
            "type": actionType,
            "target": targetField.text.trim(),
            "arguments": argsField.text.trim(),
            "working_dir": workdirField.text.trim(),
            "run_as": adminSwitch.checked ? "admin" : "user",
            "keyboard_steps": actionType === "keyboard" ? steps : []
        }
    }

    // 保存前的校验；没问题时返回空串。
    function validate() {
        if (actionType === "keyboard") {
            if (steps.length === 0) {
                // 一步都没有的按键动作点了也不会发生任何事，不如现在就拦住。
                return qsTr("按键动作还一步都没有，先录制或新增一条步骤")
            }
            for (var i = 0; i < steps.length; ++i) {
                var step = steps[i]
                if (step.type === "wait") {
                    continue
                }
                var hasName = String(step.key || "").trim().length > 0
                var vk = parseInt(step.vk)
                var hasCode = !isNaN(vk) && vk >= 1 && vk <= 255
                if (!hasName && !hasCode) {
                    return qsTr("第 %1 步既没有名称也没有键码").arg(i + 1)
                }
            }
            return ""
        }
        if (targetField.text.trim().length === 0) {
            return qsTr("请先填写动作目标")
        }
        return ""
    }

    function targetHint() {
        var hints = [
            qsTr("选择文件或程序，例如 notepad.exe"),
            qsTr("命令行，例如 ping"),
            qsTr("网址，例如 https://example.com"),
            qsTr("在下面的「按键序列」里配置")
        ]
        var index = typeKeys.indexOf(actionType)
        return index >= 0 ? hints[index] : hints[0]
    }

    // ------------------------------------------------------------------
    // 表单
    // ------------------------------------------------------------------
    FormRow {
        label: qsTr("类型")
        ComboBox {
            id: typeCombo
            objectName: "actionTypeCombo"
            Layout.preferredWidth: 200
            model: [qsTr("文件 / 程序"), qsTr("命令行"), qsTr("网址"), qsTr("按键模拟")]
            // 只在用户真的选了才动状态：程序回填 currentIndex 会触发
            // currentIndexChanged，用 activated 才能把「读配置」和「改配置」分开。
            onActivated: function (index) {
                form.actionType = form.typeKeys[index] || "file"
            }
        }
    }

    FormRow {
        label: qsTr("目标")
        TextField {
            id: targetField
            Layout.fillWidth: true
            placeholderText: form.targetHint()
            enabled: form.actionType !== "keyboard"
        }
        ToolButton {
            icon.name: "ic_fluent_folder_open_20_regular"
            visible: form.actionType === "file"
            ToolTip.text: qsTr("浏览文件")
            onClicked: {
                var picked = ConfigManager.pickFile()
                if (picked) {
                    targetField.text = picked
                }
            }
        }
    }

    FormRow {
        label: qsTr("参数")
        TextField {
            id: argsField
            Layout.fillWidth: true
            placeholderText: qsTr("启动参数（可选，含空格时整段加引号）")
        }
    }

    FormRow {
        label: qsTr("工作目录")
        TextField {
            id: workdirField
            Layout.fillWidth: true
            placeholderText: qsTr("留空则使用目标所在目录")
        }
    }

    FormRow {
        label: qsTr("管理员运行")
        description: qsTr("仅对文件 / 命令行类型有效")
        Switch {
            id: adminSwitch
            enabled: form.actionType === "file" || form.actionType === "cmd"
            checkedText: qsTr("是")
            uncheckedText: qsTr("否")
        }
    }

    // ── 按键序列（仅按键模拟需要）──
    Text {
        Layout.fillWidth: true
        visible: form.actionType === "keyboard"
        wrapMode: Text.Wrap
        typography: Typography.Caption
        color: Theme.currentTheme.colors.textSecondaryColor
        text: qsTr("「延迟」指这一步执行前先等多久；「按住 + 释放」能搭配出长按或组合键；"
                   + "填了键码按键码发送，否则按名称解析（组合键如 Ctrl+C 只能填在名称里）。")
    }

    KeyboardStepsEditor {
        id: keyboardEditor
        objectName: "keyboardStepsEditor"
        Layout.fillWidth: true
        visible: form.actionType === "keyboard"
        steps: form.steps
        onStepsEdited: function (nextSteps) {
            form.steps = nextSteps
        }
    }

    Text {
        Layout.fillWidth: true
        Layout.topMargin: 4
        wrapMode: Text.Wrap
        typography: Typography.Caption
        color: Theme.currentTheme.colors.textSecondaryColor
        text: qsTr("目标支持 {configdir}、{homedir}、{desktop}、{documents}、{downloads} "
                   + "等占位符，以及 %ENV% 环境变量。")
    }
}
