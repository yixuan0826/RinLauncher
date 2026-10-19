import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import RinUI

import "../components"

// 图标选择器。
//
// 四个来源分页：内置图标（RinUI 的 Fluent 字体）、随包图标（Lawnicons SVG）、
// 我的图标（导入的 svg / png / ico，以及从程序里抽出来的），还有「从文件获取」
// （程序 / 快捷方式提取，或图片直接导入）。
//
// 两处和上一版不同的取舍：
//   * 页签用 Segmented —— 自带选中态的填充与下划线，比裸 TabBar 一眼看得出；
//   * 点一下不再直接关窗，先选中、再按「使用这个图标」，免得手一抖就选错。
AppDialog {
    id: picker

    property string current: ""
    property string pendingKey: ""
    // 调用方指定打开时的页签（-1 = 按当前图标自动选）。
    property int initialTab: -1

    signal picked(string iconKey)

    readonly property int cellSize: 56

    title: qsTr("选择图标")
    preferredWidth: 780
    preferredHeight: 620
    closeOnScrim: false

    // ── 数据 ──
    property var bundledIcons: []
    property var customIcons: []
    property string extractPath: ""
    property string extractPreview: ""

    readonly property var fluentIcons: [
        "ic_fluent_home_20_regular", "ic_fluent_apps_20_regular", "ic_fluent_apps_list_20_regular",
        "ic_fluent_window_20_regular", "ic_fluent_window_new_20_regular", "ic_fluent_desktop_20_regular",
        "ic_fluent_laptop_20_regular", "ic_fluent_phone_20_regular", "ic_fluent_tablet_20_regular",
        "ic_fluent_folder_20_regular", "ic_fluent_folder_open_20_regular", "ic_fluent_folder_zip_20_regular",
        "ic_fluent_document_20_regular", "ic_fluent_document_text_20_regular", "ic_fluent_book_20_regular",
        "ic_fluent_code_20_regular", "ic_fluent_database_20_regular", "ic_fluent_server_20_regular",
        "ic_fluent_settings_20_regular", "ic_fluent_wrench_20_regular", "ic_fluent_toolbox_20_regular",
        "ic_fluent_search_20_regular", "ic_fluent_filter_20_regular", "ic_fluent_arrow_sort_20_regular",
        "ic_fluent_globe_20_regular", "ic_fluent_link_20_regular", "ic_fluent_link_square_20_regular",
        "ic_fluent_open_20_regular", "ic_fluent_arrow_import_20_regular", "ic_fluent_arrow_export_20_regular",
        "ic_fluent_arrow_download_20_regular", "ic_fluent_arrow_upload_20_regular",
        "ic_fluent_arrow_sync_20_regular", "ic_fluent_arrow_repeat_all_20_regular",
        "ic_fluent_play_20_regular", "ic_fluent_pause_20_regular", "ic_fluent_stop_20_regular",
        "ic_fluent_music_note_2_20_regular", "ic_fluent_headphones_20_regular", "ic_fluent_speaker_2_20_regular",
        "ic_fluent_image_20_regular", "ic_fluent_camera_20_regular", "ic_fluent_tv_20_regular",
        "ic_fluent_video_20_regular", "ic_fluent_paint_brush_20_regular", "ic_fluent_color_20_regular",
        "ic_fluent_text_font_20_regular", "ic_fluent_text_align_left_20_regular",
        "ic_fluent_pen_20_regular", "ic_fluent_edit_20_regular", "ic_fluent_copy_20_regular",
        "ic_fluent_save_20_regular", "ic_fluent_bookmark_20_regular", "ic_fluent_bookmark_multiple_20_regular",
        "ic_fluent_collections_20_regular", "ic_fluent_library_20_regular", "ic_fluent_list_20_regular",
        "ic_fluent_grid_20_regular", "ic_fluent_board_20_regular", "ic_fluent_panel_left_20_regular",
        "ic_fluent_split_horizontal_20_regular", "ic_fluent_box_multiple_20_regular",
        "ic_fluent_add_20_regular", "ic_fluent_delete_20_regular", "ic_fluent_dismiss_20_regular",
        "ic_fluent_checkmark_circle_20_regular", "ic_fluent_question_circle_20_regular",
        "ic_fluent_info_20_regular", "ic_fluent_star_20_regular", "ic_fluent_star_add_20_regular",
        "ic_fluent_rocket_20_regular", "ic_fluent_fire_20_regular", "ic_fluent_flash_20_regular",
        "ic_fluent_sparkle_20_regular", "ic_fluent_wand_20_regular", "ic_fluent_joystick_20_regular",
        "ic_fluent_puzzle_piece_20_regular", "ic_fluent_slide_text_20_regular",
        "ic_fluent_certificate_20_regular", "ic_fluent_shield_20_regular", "ic_fluent_shield_checkmark_20_regular",
        "ic_fluent_keyboard_20_regular", "ic_fluent_keyboard_123_20_regular", "ic_fluent_clock_20_regular",
        "ic_fluent_pin_20_regular", "ic_fluent_map_pin_20_regular", "ic_fluent_note_pin_20_regular",
        "ic_fluent_person_20_regular", "ic_fluent_people_20_regular", "ic_fluent_eye_20_regular",
        "ic_fluent_eye_off_20_regular", "ic_fluent_data_usage_20_regular", "ic_fluent_ribbon_20_regular",
        "ic_fluent_broom_20_regular", "ic_fluent_power_20_regular", "ic_fluent_print_20_regular",
        "ic_fluent_calculator_20_regular", "ic_fluent_food_20_regular", "ic_fluent_drop_20_regular",
        "ic_fluent_arrow_reset_20_regular", "ic_fluent_reorder_20_regular",
        "ic_fluent_more_horizontal_20_regular", "ic_fluent_more_vertical_20_regular",
        "ic_fluent_arrow_up_20_regular", "ic_fluent_arrow_down_20_regular",
        "ic_fluent_arrow_left_20_regular", "ic_fluent_arrow_right_20_regular",
        "ic_fluent_hard_drive_20_regular", "ic_fluent_usb_plug_20_regular",
        "ic_fluent_wifi_1_20_regular", "ic_fluent_bluetooth_20_regular",
        "ic_fluent_mail_20_regular", "ic_fluent_chat_20_regular", "ic_fluent_call_20_regular",
        "ic_fluent_calendar_20_regular", "ic_fluent_cloud_20_regular", "ic_fluent_weather_sunny_20_regular",
        "ic_fluent_bug_20_regular", "ic_fluent_task_list_20_regular", "ic_fluent_gift_20_regular"
    ]

    onAboutToShow: {
        pendingKey = current
        extractPreview = ""
        extractPath = ""
        bundledIcons = ConfigManager.getBundledIcons().map(
            function (name) { return "lawnicons:" + name })
        reloadCustom()
        if (initialTab >= 0) {
            // 调用方指定了页签（比如编辑器里直接点「从文件获取图标…」）。
            tabs.currentIndex = initialTab
            initialTab = -1
        } else {
            // 已经是用户自己的图标，就直接落在「我的图标」页。
            tabs.currentIndex = current.indexOf("file:") === 0 ? 2
                : current.indexOf("lawnicons:") === 0 ? 1 : 0
        }
    }

    // 打开并直接翻到某一页。
    function openTab(index) {
        initialTab = index
        open()
    }

    function reloadCustom() {
        customIcons = ConfigManager.getCustomIcons()
    }

    // ------------------------------------------------------------------
    // 内容
    // ------------------------------------------------------------------
    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 12

        Segmented {
            id: tabs
            objectName: "iconTabs"
            Layout.alignment: Qt.AlignLeft
            SegmentedItem { text: qsTr("内置图标") }
            SegmentedItem { text: qsTr("随包图标") }
            SegmentedItem { text: qsTr("我的图标") }
            SegmentedItem { text: qsTr("从文件获取") }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabs.currentIndex

            // ── 0：内置 Fluent 图标 ──
            ColumnLayout {
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("内置 Fluent 图标（%1）")
                        .arg(picker.fluentIcons.length)
                }

                IconGrid {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    icons: picker.fluentIcons
                    cellSize: picker.cellSize
                    selectedKey: picker.pendingKey
                    onPicked: picker.pendingKey = iconKey
                }
            }

            // ── 1：随包 Lawnicons ──
            ColumnLayout {
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("随包图标（%1），会跟着主题色变化")
                        .arg(picker.bundledIcons.length)
                }

                IconGrid {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    icons: picker.bundledIcons
                    cellSize: picker.cellSize
                    selectedKey: picker.pendingKey
                    onPicked: picker.pendingKey = iconKey
                }
            }

            // ── 2：我的图标 ──
            ColumnLayout {
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("我的图标（%1）")
                            .arg(picker.customIcons.length)
                    }
                    Button {
                        text: qsTr("添加图标")
                        icon.name: "ic_fluent_add_20_regular"
                        onClicked: {
                            var key = ConfigManager.importIcon()
                            if (key.length > 0) {
                                picker.pendingKey = key
                                picker.reloadCustom()
                            }
                        }
                    }
                    Button {
                        text: qsTr("打开图标目录")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: ConfigManager.openIconFolder()
                    }
                }

                IconGrid {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    icons: picker.customIcons.map(function (item) { return item.key })
                    cellSize: picker.cellSize
                    tint: Theme.currentTheme.colors.textColor
                    selectedKey: picker.pendingKey
                    deletable: true
                    onPicked: picker.pendingKey = iconKey
                    onRemoveRequested: {
                        if (ConfigManager.deleteCustomIcon(iconKey)) {
                            if (picker.pendingKey === iconKey) {
                                picker.pendingKey = ""
                            }
                            picker.reloadCustom()
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: picker.customIcons.length === 0
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("图标库还是空的。点「添加图标」挑一张图片，"
                               + "或到「从文件获取」页把程序 / 快捷方式的图标取出来。")
                }
            }

            // ── 3：从文件获取（程序提取 / 图片导入）──
            ColumnLayout {
                spacing: 10

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("选一个 exe / dll / lnk，程序会向系统要它的图标（快捷方式跟随目标，"
                               + "拿到的是程序自己的图标）；也可以直接挑一张 ico / svg / png 图片。"
                               + "结果都会存进图标库，之后在别处可以复用。")
                }

                FormRow {
                    label: qsTr("文件")
                    TextField {
                        Layout.fillWidth: true
                        placeholderText: qsTr("程序、快捷方式或图片的路径")
                        text: picker.extractPath
                        onTextChanged: picker.extractPath = text
                    }
                    Button {
                        text: qsTr("浏览…")
                        icon.name: "ic_fluent_folder_open_20_regular"
                        onClicked: {
                            var path = ConfigManager.pickIconSource()
                            if (path.length > 0) {
                                picker.extractPath = path
                            }
                        }
                    }
                    Button {
                        text: qsTr("获取图标")
                        icon.name: "ic_fluent_arrow_download_20_regular"
                        highlighted: true
                        enabled: picker.extractPath.length > 0
                        onClicked: {
                            var key = ConfigManager.acquireIcon(picker.extractPath)
                            if (key.length > 0) {
                                picker.extractPreview = key
                                picker.pendingKey = key
                                picker.reloadCustom()
                            }
                        }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 132

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 16

                        AppIcon {
                            Layout.alignment: Qt.AlignVCenter
                            iconKey: picker.extractPreview
                            iconSize: 64
                            placeholder: "ic_fluent_image_20_regular"
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 4

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.NoWrap
                                elide: Text.ElideMiddle
                                color: Theme.currentTheme.colors.textColor
                                text: picker.extractPreview.length > 0
                                    ? qsTr("已提取，可以直接使用")
                                    : qsTr("还没有提取结果")
                            }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.NoWrap
                                elide: Text.ElideMiddle
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: picker.extractPreview
                            }
                        }

                        Button {
                            Layout.alignment: Qt.AlignVCenter
                            text: qsTr("去图标库看看")
                            enabled: picker.extractPreview.length > 0
                            onClicked: tabs.currentIndex = 2
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    footer: RowLayout {
        spacing: 8

        AppIcon {
            Layout.alignment: Qt.AlignVCenter
            iconKey: picker.pendingKey
            iconSize: 20
            placeholder: "ic_fluent_dismiss_20_regular"
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.NoWrap
            elide: Text.ElideMiddle
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: picker.pendingKey.length > 0 ? picker.pendingKey : qsTr("未选择")
        }

        Button {
            text: qsTr("取消")
            onClicked: picker.reject()
        }

        Button {
            text: qsTr("使用这个图标")
            highlighted: true
            enabled: picker.pendingKey.length > 0
            onClicked: {
                picker.picked(picker.pendingKey)
                picker.accept()
            }
        }
    }
}
