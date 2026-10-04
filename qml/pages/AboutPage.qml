import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 关于。
//
// 从设置页里搬出来单独成页 —— 塞在设置最底下的那三行信息既不好找，也放不下
// 运行环境和第三方组件这些该写清楚的东西。
Item {
    id: aboutPage

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

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            spacing: 8

            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 0
                Text {
                    font.bold: true
                    font.pixelSize: Theme.currentTheme.typography.bodySize + 4
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("关于")
                }
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("版本、运行环境与第三方组件")
                }
            }

            Item { Layout.fillWidth: true }
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: contentColumn.implicitHeight + 28
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: contentColumn
                x: 16
                width: scroller.width - 32
                spacing: 16

                // ── 主卡片 ──
                Frame {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 152

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 20

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: "url:" + Qt.resolvedUrl("../../assets/icon.png")
                            iconSize: 72
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
                                    text: qsTr("v%1").arg(aboutPage.runtime.version || "-")
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: qsTr("常驻桌面右下角的启动台小窗 + 一个把东西管起来的完整窗口："
                                           + "面板格子随手点，内容在启动台里直接编辑，图标可以自己导入。")
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Button {
                                    text: qsTr("项目仓库")
                                    icon.name: "ic_fluent_open_20_regular"
                                    onClicked: Qt.openUrlExternally(aboutPage.repoUrl)
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
                            text: aboutPage.runtime.version || "-"
                        }
                    }
                    FormRow {
                        label: qsTr("Python")
                        Text {
                            color: Theme.currentTheme.colors.textColor
                            text: aboutPage.runtime.python || "-"
                        }
                    }
                    FormRow {
                        label: qsTr("Qt / PySide6")
                        Text {
                            color: Theme.currentTheme.colors.textColor
                            text: qsTr("%1 / %2")
                                .arg(aboutPage.runtime.qt || "-")
                                .arg(aboutPage.runtime.pyside || "-")
                        }
                    }
                    FormRow {
                        label: qsTr("系统")
                        Text {
                            color: Theme.currentTheme.colors.textColor
                            text: aboutPage.runtime.system || "-"
                        }
                    }
                    FormRow {
                        label: qsTr("配置目录")
                        Text {
                            Layout.fillWidth: true
                            wrapMode: Text.NoWrap
                            elide: Text.ElideMiddle
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: aboutPage.runtime.configDir || "-"
                        }
                        ToolButton {
                            icon.name: "ic_fluent_folder_open_20_regular"
                            ToolTip.text: qsTr("打开")
                            onClicked: ConfigManager.openConfigFolder()
                        }
                    }
                }

                // ── 快捷入口 ──
                SettingsGroup {
                    iconKey: "ic_fluent_wrench_20_regular"
                    title: qsTr("快捷入口")

                    FormRow {
                        label: qsTr("配置与日志")
                        description: qsTr("排查问题的时候多半要看这两处")
                        RowLayout {
                            spacing: 8
                            Button {
                                text: qsTr("配置目录")
                                icon.name: "ic_fluent_folder_open_20_regular"
                                onClicked: ConfigManager.openConfigFolder()
                            }
                            Button {
                                text: qsTr("配置文件")
                                icon.name: "ic_fluent_document_20_regular"
                                onClicked: ConfigManager.openConfigFile()
                            }
                            Button {
                                text: qsTr("图标库")
                                icon.name: "ic_fluent_image_20_regular"
                                onClicked: ConfigManager.openIconFolder()
                            }
                        }
                    }

                    FormRow {
                        label: qsTr("重新加载")
                        description: qsTr("从磁盘重读配置；手改过 YAML 之后点这里")
                        Button {
                            text: qsTr("重载配置")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            onClicked: ConfigManager.reloadConfig()
                        }
                    }
                }

                // ── 许可证 ──
                SettingsGroup {
                    iconKey: "ic_fluent_certificate_20_regular"
                    title: qsTr("许可证")

                    FormRow {
                        label: qsTr("本项目")
                        description: qsTr("以 MIT 许可证发布")
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
                        text: qsTr("Lawnicons 的图标为适配 Qt 做过修改（补 viewBox），"
                                   + "已按 Apache-2.0 §4(b) 在 assets/icons/lawnicons/NOTICE 中标注。")
                    }

                    Repeater {
                        model: aboutPage.components

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
                }
            }
        }
    }

    Component.onCompleted: reload()

    function reload() {
        runtime = ConfigManager.getRuntimeInfo()
    }
}
