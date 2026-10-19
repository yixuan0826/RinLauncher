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

    // (组件, 许可证, 链接, 说明)
    readonly property var components: [
        {"name": "RinUI", "license": "MIT",
         "url": "https://github.com/RinLit-233-shiroko/Rin-UI",
         "note": "Fluent Design 风格的 QML 控件库，已内联在本仓库"},
        {"name": "Lawnicons", "license": "Apache-2.0",
         "url": "https://github.com/LawnchairLauncher/lawnicons",
         "note": "随包附带的通用图标，为适配 Qt 补过 viewBox"},
        {"name": "Fluent UI System Icons", "license": "MIT",
         "url": "https://github.com/microsoft/fluentui-system-icons",
         "note": "界面里的字体图标，随 RinUI 提供"},
        {"name": "PySide6 / Qt", "license": "LGPL-3.0",
         "url": "https://www.qt.io/qt-for-python",
         "note": "Python 的 Qt 绑定与运行时"}
    ]

    Layout.fillWidth: true
    spacing: 16

    // ── 主卡片 ──
    Frame {
        Layout.fillWidth: true
        Layout.preferredHeight: 140

        RowLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 20

            AppIcon {
                Layout.alignment: Qt.AlignVCenter
                iconKey: "url:" + Qt.resolvedUrl("../../assets/icon.png")
                iconSize: 64
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
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("常驻桌面右下角的启动台小窗，配独立的启动台编辑窗口与设置窗口。")
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
            label: qsTr("程序版本")
            Text {
                color: Theme.currentTheme.colors.textColor
                text: aboutSection.runtime.version || "-"
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

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("Rin Launcher 以 MIT 许可证发布。下面这些项目直接或间接地撑起了它，"
                       + "在此逐一致谢。")
        }

        Repeater {
            model: aboutSection.components

            delegate: Frame {
                Layout.fillWidth: true
                implicitHeight: 56

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 80
                        spacing: 0

                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            color: Theme.currentTheme.colors.textColor
                            text: modelData.name
                        }
                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: modelData.note
                        }
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
            text: qsTr("其他依赖：pycaw、comtypes、pywinrt（MIT）、PyYAML（MIT）、"
                       + "darkdetect（MIT）、pynput（LGPL-3.0）、watchdog（Apache-2.0）、"
                       + "pywin32（PSF-2.0）。Lawnicons 的图标为适配 Qt 做过修改（补 viewBox），"
                       + "已按 Apache-2.0 §4(b) 在 assets/icons/lawnicons/NOTICE 中标注。")
        }
    }

    Component.onCompleted: reload()

    function reload() {
        runtime = ConfigManager.getRuntimeInfo()
    }
}
