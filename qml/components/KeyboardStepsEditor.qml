import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

// 按键序列编辑器：录制 + 列表 + 底部编辑行，布局照 SystemTools 的「模拟键盘」重做。
//
// 数据是 [{type:"key", key, vk, action, duration}]：duration 是这一步执行前的等待
// （秒），vk 是虚拟键码（缺省 / 为 0 时执行端按 key 名称解析，支持 Ctrl+C 组合键）。
// 旧版「等待」步骤仍会显示：只能改延迟或删除。
//
// 本组件不直接改数组 —— 所有修改整表经 stepsEdited 发回给持有者（ActionForm）；
// 录制中由 KeyRecorder.stepsChanged 推送整表。
ColumnLayout {
    id: root

    property var steps: []
    property int selectedIndex: -1
    property bool recording: false
    property bool nameEdited: false   // 用户在「名称」里动过键盘
    property bool codeEdited: false   // 用户在「键码」里动过键盘
    property string hint: ""
    property bool hintError: false

    readonly property var actionValues: ["click", "press", "release"]
    readonly property var actionLabels: [qsTr("单击"), qsTr("按住"), qsTr("释放")]
    readonly property bool available: typeof KeyRecorder !== "undefined"
        && KeyRecorder !== null && KeyRecorder.available

    // 修改后的完整数组由这里交给持有者保存。
    signal stepsEdited(var nextSteps)

    Layout.fillWidth: true
    spacing: 8

    onVisibleChanged: {
        // 表单切走（换类型 / 关窗）时顺手结束录制，别让监听一直挂着。
        if (!visible && root.recording) {
            root.stopRecording()
        }
    }

    Component.onDestruction: {
        if (root.recording) {
            root.stopRecording()
        }
    }

    onStepsChanged: {
        // 外部换了数据（打开另一个槽位）时，别让选中态指向不存在的行。
        if (root.selectedIndex >= root.steps.length) {
            root.selectedIndex = -1
            root.refreshEnabled()
        }
    }

    Connections {
        target: typeof KeyRecorder !== "undefined" && KeyRecorder !== null ? KeyRecorder : null

        function onStepsChanged(list) {
            // 录制结果整表替换。
            root.selectedIndex = -1
            root.hint = ""
            root.stepsEdited(list)
        }

        function onRecordingChanged(active) {
            root.recording = active
            root.refreshEnabled()
            if (active) {
                root.selectedIndex = -1
                root.hint = ""
            }
        }
    }

    // ------------------------------------------------------------------
    // 录制
    // ------------------------------------------------------------------
    function startRecording() {
        if (typeof KeyRecorder !== "undefined" && KeyRecorder !== null) {
            KeyRecorder.start()
        }
    }

    function stopRecording() {
        if (typeof KeyRecorder !== "undefined" && KeyRecorder !== null) {
            KeyRecorder.stop()
        }
    }

    // ------------------------------------------------------------------
    // 列表 <-> 编辑行
    // ------------------------------------------------------------------
    function describe(index, step) {
        if (!step) {
            return ""
        }
        var ms = Math.round((step.duration || 0) * 1000)
        var prefix = (index + 1) + ". [" + ms + "ms] "
        if (step.type === "wait") {
            return prefix + qsTr("等待")
        }
        var labelIndex = Math.max(0, root.actionValues.indexOf(step.action || "click"))
        var name = String(step.key || "").trim()
        var vk = parseInt(step.vk)
        var hasCode = !isNaN(vk) && vk >= 1 && vk <= 255
        var keyPart = name.length > 0 ? name
                                      : (hasCode ? qsTr("键码 %1").arg(vk) : qsTr("未设置"))
        if (name.length > 0 && hasCode) {
            keyPart += " (" + vk + ")"
        }
        return prefix + root.actionLabels[labelIndex] + " " + keyPart
    }

    function selectStep(index) {
        if (index < 0 || index >= root.steps.length) {
            return
        }
        root.selectedIndex = index
        root.loadStep(root.steps[index])
        root.refreshEnabled()
    }

    function loadStep(step) {
        root.nameEdited = false
        root.codeEdited = false
        root.hint = ""
        root.hintError = false
        var isWait = step.type === "wait"
        if (!isWait) {
            actionCombo.currentIndex = Math.max(0, root.actionValues.indexOf(step.action || "click"))
        }
        var vk = parseInt(step.vk)
        vkField.text = (!isWait && vk >= 1 && vk <= 255) ? String(vk) : ""
        nameField.text = isWait ? "" : String(step.key || "")
        delayField.text = String(Math.round((step.duration || 0) * 1000))
        if (isWait) {
            root.hint = qsTr("这是旧版「等待」步骤：只能改延迟或删除。")
        }
    }

    // 编辑行放在选中行 / 录制状态下该不该可编辑：
    // 没选中时也要能输入 —— 手填一条再点「新增」是常用姿势。
    function refreshEnabled() {
        var hasSelection = root.selectedIndex >= 0 && root.selectedIndex < root.steps.length
        var isWait = hasSelection && root.steps[root.selectedIndex].type === "wait"
        actionCombo.enabled = !root.recording && !isWait
        vkField.enabled = !root.recording && !isWait
        nameField.enabled = !root.recording && !isWait
        delayField.enabled = !root.recording
    }

    function resetSelection() {
        root.selectedIndex = -1
        root.nameEdited = false
        root.codeEdited = false
        root.hint = ""
        root.hintError = false
        actionCombo.currentIndex = 0
        vkField.text = ""
        nameField.text = ""
        delayField.text = ""
        root.refreshEnabled()
    }

    // ------------------------------------------------------------------
    // 编辑动作
    // ------------------------------------------------------------------
    // appendMode = true 时是「新增」，否则把编辑行应用到选中行。
    function commitEdit(appendMode) {
        if (root.recording) {
            return
        }
        var ms = parseInt(delayField.text)
        if (isNaN(ms) || ms < 0) {
            ms = 0
        }
        var name = nameField.text.trim()
        var code = parseInt(vkField.text)
        var hasCode = !isNaN(code) && code >= 1 && code <= 255

        var hasSelection = root.selectedIndex >= 0 && root.selectedIndex < root.steps.length
        var isWaitEdit = !appendMode && hasSelection && root.steps[root.selectedIndex].type === "wait"

        var next = root.steps.slice()
        if (isWaitEdit) {
            // 旧版等待步骤：只有延迟有得改。
            next[root.selectedIndex] = { "type": "wait", "duration": ms / 1000 }
            root.hint = ""
            root.hintError = false
            root.stepsEdited(next)
            return
        }

        if (!hasCode && name.length === 0) {
            root.hint = qsTr("先填「名称」，或 1-255 的「键码」")
            root.hintError = true
            return
        }

        var step = {
            "type": "key",
            "key": name,
            "action": root.actionValues[Math.max(0, actionCombo.currentIndex)] || "click",
            "duration": ms / 1000
        }
        // 键码优先级（照 SystemTools：执行看键码，名称只是显示）：
        // * 只改过「名称」且填了内容 → 交给名称（组合键只能这样表达）；
        // * 名称里带 +（组合键）→ 同样走名称；
        // * 其余情况填了键码就带上。
        var nameTakesOver = root.nameEdited && !root.codeEdited && name.length > 0
        if (hasCode && !nameTakesOver && name.indexOf("+") === -1) {
            step["vk"] = code
        }

        if (appendMode) {
            next.push(step)
            root.selectedIndex = next.length - 1
        } else {
            if (!hasSelection) {
                return
            }
            next[root.selectedIndex] = step
        }
        root.hint = ""
        root.hintError = false
        root.stepsEdited(next)
        root.refreshEnabled()
    }

    function removeSelected() {
        if (root.recording || root.selectedIndex < 0 || root.selectedIndex >= root.steps.length) {
            return
        }
        var next = root.steps.slice()
        next.splice(root.selectedIndex, 1)
        root.selectedIndex = -1
        root.hint = ""
        root.hintError = false
        root.stepsEdited(next)
        root.refreshEnabled()
    }

    Component.onCompleted: root.refreshEnabled()

    // ------------------------------------------------------------------
    // 界面
    // ------------------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Button {
            objectName: "keyboardRecordButton"
            text: root.recording ? qsTr("结束录制") : qsTr("开始录制键盘输入")
            icon.name: root.recording ? "ic_fluent_stop_20_regular" : "ic_fluent_record_20_regular"
            enabled: root.available
            onClicked: {
                if (root.recording) {
                    root.stopRecording()
                } else {
                    root.startRecording()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            wrapMode: Text.Wrap
            typography: Typography.Caption
            color: root.recording
                   ? Theme.currentTheme.colors.systemCriticalColor
                   : Theme.currentTheme.colors.textSecondaryColor
            text: root.recording
                  ? qsTr("正在录制，直接敲键盘即可。")
                  : qsTr("录制会整理成步骤，也可以在下方手动新增。")
        }
    }

    Frame {
        Layout.fillWidth: true
        Layout.preferredHeight: 168
        hoverable: false

        ListView {
            id: stepsList
            objectName: "keyboardStepsList"
            anchors.fill: parent
            anchors.margins: 6
            clip: true
            spacing: 2
            model: root.steps
            ScrollBar.vertical: ScrollBar {}

            delegate: Rectangle {
                id: row

                required property int index
                required property var modelData

                width: stepsList.width
                height: 30
                radius: 6
                color: row.index === root.selectedIndex
                       ? Theme.currentTheme.colors.subtleSecondaryColor
                       : (rowMouse.containsMouse ? Theme.currentTheme.colors.controlSecondaryColor
                                                 : "transparent")

                Rectangle {
                    // 选中行的左侧强调条
                    visible: row.index === root.selectedIndex
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 2
                    width: 3
                    height: parent.height - 12
                    radius: 1.5
                    color: Theme.currentTheme.colors.primaryColor
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    elide: Text.ElideRight
                    color: Theme.currentTheme.colors.textColor
                    text: root.describe(row.index, row.modelData)
                }

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.selectStep(row.index)
                }
            }
        }

        Text {
            anchors.centerIn: parent
            width: parent.width - 32
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            visible: root.steps.length === 0
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: root.recording
                  ? qsTr("正在录制…")
                  : qsTr("还没有步骤。")
        }
    }

    Flow {
        Layout.fillWidth: true
        spacing: 14

        Row {
            spacing: 6

            Text {
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.currentTheme.colors.textColor
                text: qsTr("操作")
            }

            ComboBox {
                id: actionCombo
                objectName: "keyboardActionCombo"
                width: 110
                model: root.actionLabels
            }
        }

        Row {
            spacing: 6

            Text {
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.currentTheme.colors.textColor
                text: qsTr("键码")
            }

            TextField {
                id: vkField
                objectName: "keyboardVkField"
                width: 96
                placeholderText: qsTr("虚拟键码")
                validator: IntValidator { bottom: 0; top: 255 }
                onTextEdited: {
                    root.codeEdited = true
                    root.hint = ""
                    root.hintError = false
                }
            }
        }

        Row {
            spacing: 6

            Text {
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.currentTheme.colors.textColor
                text: qsTr("名称")
            }

            TextField {
                id: nameField
                objectName: "keyboardNameField"
                width: 150
                placeholderText: qsTr("按键名称")
                onTextEdited: {
                    root.nameEdited = true
                    root.hint = ""
                    root.hintError = false
                }
            }
        }

        Row {
            spacing: 6

            Text {
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.currentTheme.colors.textColor
                text: qsTr("延迟")
            }

            TextField {
                id: delayField
                objectName: "keyboardDelayField"
                width: 110
                placeholderText: qsTr("延迟(ms)")
                validator: IntValidator { bottom: 0; top: 3600000 }
                onTextEdited: {
                    root.hint = ""
                    root.hintError = false
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Button {
            objectName: "keyboardApplyButton"
            text: qsTr("应用修改")
            enabled: !root.recording && root.selectedIndex >= 0 && root.selectedIndex < root.steps.length
            onClicked: root.commitEdit(false)
        }

        Button {
            objectName: "keyboardAddButton"
            text: qsTr("新增")
            enabled: !root.recording
            onClicked: root.commitEdit(true)
        }

        Button {
            objectName: "keyboardDeleteButton"
            text: qsTr("删除")
            enabled: !root.recording && root.selectedIndex >= 0 && root.selectedIndex < root.steps.length
            onClicked: root.removeSelected()
        }

        Item { Layout.fillWidth: true }

        Text {
            Layout.alignment: Qt.AlignVCenter
            visible: root.hint.length > 0
            color: root.hintError
                   ? Theme.currentTheme.colors.systemCriticalColor
                   : Theme.currentTheme.colors.textSecondaryColor
            text: root.hint
        }
    }
}
