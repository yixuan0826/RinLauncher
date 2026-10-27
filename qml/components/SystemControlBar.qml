import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

// 启动台底部的系统控制条：系统音量 + Wi-Fi + 移动热点。
//
// 样式对齐 Windows 11 快速设置：一排圆角卡片，开启状态用主色淡底，
// 音量卡占剩余宽度，两个开关卡是等宽方块。后端是 SystemControls
// （rin_launcher/system_controls.py，main.py 里注入的 context property）。
RowLayout {
    id: root

    spacing: 8

    // context property 在窗口销毁阶段会先变成 null，用带保护的别名承接，
    // 免得引擎析构时刷一屏 “Cannot read property of null”。
    readonly property var sys: SystemControls
    readonly property real volumeValue: sys ? sys.volume : 0
    readonly property bool mutedValue: sys ? sys.muted : false
    readonly property bool wifiAvailableValue: sys ? sys.wifiAvailable : false
    readonly property bool wifiEnabledValue: sys ? sys.wifiEnabled : false
    readonly property bool wifiBusyValue: sys ? sys.wifiBusy : false
    readonly property string wifiSsidValue: sys ? sys.wifiSsid : ""
    readonly property bool hotspotAvailableValue: sys ? sys.hotspotAvailable : false
    readonly property bool hotspotEnabledValue: sys ? sys.hotspotEnabled : false
    readonly property bool hotspotBusyValue: sys ? sys.hotspotBusy : false
    readonly property string hotspotSsidValue: sys ? sys.hotspotSsid : "rinlauncher-hotspot"
    readonly property string hotspotPasswordValue: sys ? sys.hotspotPassword : "12345678"

    readonly property color activeBackground: Qt.rgba(
        Theme.currentTheme.colors.primaryColor.r,
        Theme.currentTheme.colors.primaryColor.g,
        Theme.currentTheme.colors.primaryColor.b,
        0.20)
    readonly property color tileColor: Theme.currentTheme.colors.cardColor
    // 悬停用更亮一层的卡片色（浅色主题是纯白，深色主题是 7% 白），
    // 比同样是半透明白的 controlSecondaryColor 明显得多。
    readonly property color hoverColor: Theme.currentTheme.colors.cardTertiaryColor
    readonly property color textMain: Theme.currentTheme.colors.textColor
    readonly property color textSub: Theme.currentTheme.colors.textSecondaryColor
    // 开启状态的图标 / 文字不再上强调色：只靠背景高亮区分开与关。
    readonly property color activeText: Theme.currentTheme.colors.textColor

    function background(active, hovered) {
        return active ? activeBackground : (hovered ? hoverColor : tileColor)
    }

    function volumeIcon() {
        if (root.mutedValue || root.volumeValue <= 0.001) {
            return "ic_fluent_speaker_mute_20_regular"
        }
        if (root.volumeValue < 0.34) {
            return "ic_fluent_speaker_0_20_regular"
        }
        if (root.volumeValue < 0.67) {
            return "ic_fluent_speaker_1_20_regular"
        }
        return "ic_fluent_speaker_2_20_regular"
    }

    function wifiStatus() {
        if (root.wifiBusyValue) {
            return qsTr("切换中…")
        }
        if (!root.wifiAvailableValue) {
            return qsTr("不可用")
        }
        if (!root.wifiEnabledValue) {
            return qsTr("已关闭")
        }
        return root.wifiSsidValue.length > 0 ? root.wifiSsidValue : qsTr("已开启")
    }

    function hotspotStatus() {
        if (root.hotspotBusyValue) {
            return qsTr("切换中…")
        }
        if (!root.hotspotAvailableValue) {
            return qsTr("不可用")
        }
        return root.hotspotEnabledValue ? qsTr("已开启") : qsTr("已关闭")
    }

    // ── 音量卡：图标 + 百分比 + 滑条 ──
    Frame {
        id: volumeCard
        objectName: "systemVolumeCard"

        Layout.fillWidth: true
        Layout.minimumWidth: 144
        Layout.preferredWidth: 160
        Layout.preferredHeight: 66
        hoverable: true
        padding: 0
        radius: Theme.currentTheme.appearance.windowRadius

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.topMargin: 6
            anchors.bottomMargin: 4
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Item {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20

                    AppIcon {
                        anchors.fill: parent
                        iconKey: root.volumeIcon()
                        iconSize: 20
                        tint: root.mutedValue ? root.textSub : root.activeText
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: SystemControls.toggleMute()
                    }

                    ToolTip.text: root.mutedValue ? qsTr("取消静音") : qsTr("静音")
                }

                Label {
                    text: qsTr("音量")
                    color: root.textMain
                    font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                    font.weight: Font.DemiBold
                }

                Item { Layout.fillWidth: true }

                Label {
                    text: Math.round(root.volumeValue * 100) + "%"
                    color: root.textSub
                    font.pixelSize: Theme.currentTheme.typography.captionSize
                }
            }

            Slider {
                id: volumeSlider

                Layout.fillWidth: true
                Layout.preferredHeight: 28
                from: 0
                to: 100
                stepSize: 1
                handleSize: 14
                trackHeight: 4
                onMoved: SystemControls.setVolume(value / 100)
            }
        }

        // 拖动时不要被 3 秒轮询回写，避免手柄来回跳。
        Connections {
            target: SystemControls

            function onVolumeChanged() {
                if (!volumeSlider.pressed) {
                    volumeSlider.value = Math.round(root.volumeValue * 100)
                }
            }
        }

        Component.onCompleted: {
            volumeSlider.value = Math.round(root.volumeValue * 100)
        }

        ToolTip.text: qsTr("调整系统音量")
    }

    // ── Wi-Fi 开关卡 ──
    Frame {
        id: wifiCard
        objectName: "systemWifiCard"

        Layout.preferredWidth: 100
        Layout.preferredHeight: 66
        Layout.minimumWidth: 100
        hoverable: true
        padding: 0
        radius: Theme.currentTheme.appearance.windowRadius
        color: root.background(root.wifiEnabledValue, wifiMouse.containsMouse)

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 9
            anchors.rightMargin: 8
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                AppIcon {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    iconKey: root.wifiEnabledValue
                        ? "ic_fluent_wifi_1_20_regular"
                        : "ic_fluent_wifi_off_20_regular"
                    iconSize: 20
                    tint: root.wifiEnabledValue ? root.activeText : root.textSub
                    opacity: root.wifiAvailableValue ? 1 : 0.55
                }

                Label {
                    Layout.fillWidth: true
                    objectName: "wifiTitleLabel"
                    text: qsTr("Wi-Fi")
                    color: root.wifiEnabledValue ? root.activeText : root.textMain
                    font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }

            Item { Layout.fillHeight: true }

            Label {
                Layout.fillWidth: true
                text: root.wifiStatus()
                color: root.textSub
                font.pixelSize: Theme.currentTheme.typography.captionSize
                elide: Text.ElideRight
            }
        }

        MouseArea {
            id: wifiMouse

            anchors.fill: parent
            hoverEnabled: true
            enabled: root.wifiAvailableValue && !root.wifiBusyValue
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: SystemControls.toggleWifi()
        }

        ToolTip.text: root.wifiAvailableValue
            ? qsTr("Wi-Fi 开关")
            : qsTr("没有可用的 Wi-Fi 无线网卡")
    }

    // ── 移动热点开关卡 ──
    Frame {
        id: hotspotCard
        objectName: "systemHotspotCard"

        Layout.preferredWidth: 100
        Layout.preferredHeight: 66
        Layout.minimumWidth: 100
        hoverable: true
        padding: 0
        radius: Theme.currentTheme.appearance.windowRadius
        color: root.background(root.hotspotEnabledValue, hotspotMouse.containsMouse)

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 9
            anchors.rightMargin: 8
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                AppIcon {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    iconKey: "ic_fluent_router_20_regular"
                    iconSize: 20
                    tint: root.hotspotEnabledValue ? root.activeText : root.textSub
                    opacity: root.hotspotAvailableValue ? 1 : 0.55
                }

                Label {
                    Layout.fillWidth: true
                    objectName: "hotspotTitleLabel"
                    text: qsTr("热点")
                    color: root.hotspotEnabledValue ? root.activeText : root.textMain
                    font.pixelSize: Theme.currentTheme.typography.bodyStrongSize
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }

            Item { Layout.fillHeight: true }

            Label {
                Layout.fillWidth: true
                text: root.hotspotStatus()
                color: root.textSub
                font.pixelSize: Theme.currentTheme.typography.captionSize
                elide: Text.ElideRight
            }
        }

        MouseArea {
            id: hotspotMouse

            anchors.fill: parent
            hoverEnabled: true
            enabled: root.hotspotAvailableValue && !root.hotspotBusyValue
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: SystemControls.toggleHotspot()
        }

        ToolTip.text: root.hotspotEnabledValue
            ? qsTr("热点：%1\n密码：%2").arg(root.hotspotSsidValue).arg(root.hotspotPasswordValue)
            : (root.hotspotAvailableValue
                ? qsTr("移动热点开关")
                : qsTr("移动热点不可用（没有可共享的网络连接）"))
    }
}
