import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 「关于与鸣谢」分类的内容：版本卡、运行环境、鸣谢与许可证。
ColumnLayout {
    id: aboutSection

    property var runtime: ({})

    readonly property string repoUrl: "https://github.com/yixuan0826/RinLauncher"

    // (组件, 许可证, 链接)
    readonly property var components: [
        {"name": "RinUI", "license": "MIT",
         "url": "https://github.com/RinLit-233-shiroko/Rin-UI"},
        {"name": "Lawnicons", "license": "Apache-2.0",
         "url": "https://github.com/LawnchairLauncher/lawnicons"},
        {"name": "Fluent UI System Icons", "license": "MIT",
         "url": "https://github.com/microsoft/fluentui-system-icons"},
        {"name": "PySide6 / Qt", "license": "LGPL-3.0",
         "url": "https://www.qt.io/qt-for-python"}
    ]

    Layout.fillWidth: true
    spacing: 16

    // ── 主卡片 ──
    Frame {
        Layout.fillWidth: true
        Layout.preferredHeight: 112

        RowLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 18

            AppIcon {
                Layout.alignment: Qt.AlignVCenter
                iconKey: "url:" + Qt.resolvedUrl("../../assets/icon.png")
                iconSize: 56
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        font.bold: true
                        font.pixelSize: Theme.currentTheme.typography.subtitleSize
                        color: Theme.currentTheme.colors.textColor
                        text: qsTr("Rin Launcher")
                    }
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("v%1").arg(aboutSection.runtime.version || "-")
                    }
                }

                Text {
                    visible: String(aboutSection.runtime.codename || "").length > 0
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("开发代号 %1").arg(aboutSection.runtime.codename || "")
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        text: qsTr("项目仓库")
                        icon.name: "ic_fluent_open_20_regular"
                        onClicked: Qt.openUrlExternally(aboutSection.repoUrl)
                    }
                    Button {
                        text: qsTr("RinUI 文档")
                        icon.name: "ic_fluent_book_20_regular"
                        onClicked: Qt.openUrlExternally("https://ui.rinlit.cn")
                    }
                }
            }
        }
    }

    // ── 运行环境 ──
    SettingsGroup {
        iconKey: "ic_fluent_desktop_20_regular"
        title: qsTr("运行环境")

        FormRow {
            label: qsTr("构建通道")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: aboutSection.runtime.branch || "Release"
            }
        }
        FormRow {
            label: qsTr("Python")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: aboutSection.runtime.python || "-"
            }
        }
        FormRow {
            label: qsTr("Qt / PySide6")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: qsTr("%1 / %2")
                    .arg(aboutSection.runtime.qt || "-")
                    .arg(aboutSection.runtime.pyside || "-")
            }
        }
        FormRow {
            label: qsTr("系统")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: aboutSection.runtime.system || "-"
            }
        }
        FormRow {
            label: qsTr("Windows Build")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: aboutSection.runtime.windowsBuild || "-"
            }
        }
        FormRow {
            label: qsTr("诊断信息")
            description: qsTr("复制版本、运行时和路径，方便反馈问题")
            Button {
                text: qsTr("复制")
                icon.name: "ic_fluent_copy_20_regular"
                onClicked: ConfigManager.copyDiagnostics()
            }
        }
        FormRow {
            label: qsTr("配置目录")
            Text {
                Layout.fillWidth: true
                wrapMode: Text.NoWrap
                elide: Text.ElideMiddle
                color: Theme.currentTheme.colors.textSecondaryColor
                text: aboutSection.runtime.configDir || "-"
            }
            ToolButton {
                icon.name: "ic_fluent_folder_open_20_regular"
                ToolTip.text: qsTr("打开")
                onClicked: ConfigManager.openConfigFolder()
            }
        }
    }

    // ── 鸣谢与许可证 ──
    SettingsGroup {
        iconKey: "ic_fluent_certificate_20_regular"
        title: qsTr("鸣谢与许可证")

        Repeater {
            model: aboutSection.components

            delegate: Frame {
                Layout.fillWidth: true
                implicitHeight: 44

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.NoWrap
                        elide: Text.ElideRight
                        color: Theme.currentTheme.colors.textColor
                        text: modelData.name
                    }

                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData.license
                    }

                    ToolButton {
                        icon.name: "ic_fluent_open_20_regular"
                        ToolTip.text: qsTr("打开项目主页")
                        onClicked: Qt.openUrlExternally(modelData.url)
                    }
                }
            }
        }

        FormRow {
            label: qsTr("本项目许可证")
            description: qsTr("MIT")
            Hyperlink {
                text: qsTr("查看 MIT 全文")
                openUrl: "https://opensource.org/license/mit"
            }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("其他依赖：pycaw、comtypes、pywinrt、PyYAML、darkdetect、pynput、watchdog、pywin32。")
        }
    }

    Component.onCompleted: reload()

    function reload() {
        runtime = ConfigManager.getRuntimeInfo()
    }
}
