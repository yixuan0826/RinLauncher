import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15
import RinUI

// 主窗口。
//
// 用 FluentWindow + NavigationView 而不是把内容直接塞进 FluentWindowBase：
// FluentWindowBase 的内容区是一个普通 Item（不是 Layout），窗口的直属子项用
// Layout.fillWidth/fillHeight 完全不起作用，页面会变成 0×0 的空白。
// 材质（默认增强云母）由 main.py 通过 RinUI 的 setBackdropEffect 应用，QML 这边
// 不碰原生窗口句柄。
FluentWindow {
    id: launcherWindow

    width: 1180
    height: 760
    minimumWidth: 940
    minimumHeight: 600
    title: qsTr("Rin Launcher")
    titleEnabled: false

    // 托盘菜单和设置页都通过这个属性切页：setProperty("requestedPage", "settings")。
    property string requestedPage: ""

    // 当前在设置页？（标题栏「…」菜单据此多出五个分区跳转。）
    // 注意排除 LauncherSettingsPage：它名字里也带 SettingsPage。
    readonly property bool onSettingsPage: {
        var page = String(currentPage)
        return page.indexOf("SettingsPage.qml") >= 0
            && page.indexOf("LauncherSettingsPage.qml") < 0
    }

    // 关闭按钮不直接退出，交给 Python 判断该隐藏（有托盘）还是真退出。
    signal closeRequested()

    // 页面表。左侧导航只放三个常用页；「快捷操作」这种低频入口收进了标题栏
    // 右上角的「…」菜单（openPage 照样能按名字切过去）。
    readonly property var pageUrls: ({
        "launcher": Qt.resolvedUrl("pages/LauncherSettingsPage.qml"),
        "records": Qt.resolvedUrl("pages/RecordsPage.qml"),
        "settings": Qt.resolvedUrl("pages/SettingsPage.qml"),
        "about": Qt.resolvedUrl("pages/AboutPage.qml")
    })

    navigationItems: [
        {
            "title": qsTr("启动台"),
            "icon": "ic_fluent_apps_20_regular",
            "page": pageUrls["launcher"]
        },
        {
            "title": qsTr("设置"),
            "icon": "ic_fluent_settings_20_regular",
            "page": pageUrls["settings"]
        },
        {
            "title": qsTr("关于"),
            "icon": "ic_fluent_info_20_regular",
            "page": pageUrls["about"]
        }
    ]

    onRequestedPageChanged: {
        if (requestedPage.length === 0) {
            return
        }
        var name = requestedPage
        requestedPage = ""
        openPage(name)
    }

    function openPage(name) {
        var page = pageUrls[name]
        if (page !== undefined) {
            navigationView.safePush(page, false, false)
        }
    }

    onClosing: function (close) {
        close.accepted = false
        launcherWindow.closeRequested()
    }

    // ── 标题栏右上角的「…」更多菜单 ──
    // 按钮挂在标题栏内容区的右端（最小化按钮左边），菜单贴它左下方弹出。
    Item {
        id: moreMenuHost

        objectName: "moreMenuHost"
        parent: launcherWindow.titleBarHost
        width: 34
        height: 30
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter

        ToolButton {
            anchors.fill: parent
            icon.name: "ic_fluent_more_horizontal_20_regular"
            ToolTip.text: qsTr("更多")
            ToolTip.visible: hovered
            ToolTip.delay: 500
            onClicked: launcherWindow.popupMoreMenu()
        }
    }

    Menu {
        id: moreMenu

        objectName: "moreMenu"
        position: Position.None

        // 在设置页时，菜单头顶先摆五个分区跳转 —— 设置页自己那个「…」按钮
        // 已经删掉，两套菜单合并成这一套。
        MenuItem {
            text: qsTr("常规")
            icon.name: "ic_fluent_home_20_regular"
            visible: launcherWindow.onSettingsPage
            onTriggered: ConfigManager.requestSettingsSection("generalGroup")
        }
        MenuItem {
            text: qsTr("外观")
            icon.name: "ic_fluent_color_20_regular"
            visible: launcherWindow.onSettingsPage
            onTriggered: ConfigManager.requestSettingsSection("appearanceGroup")
        }
        MenuItem {
            text: qsTr("启动台")
            icon.name: "ic_fluent_apps_20_regular"
            visible: launcherWindow.onSettingsPage
            onTriggered: ConfigManager.requestSettingsSection("launcherGroup")
        }
        MenuItem {
            text: qsTr("热键")
            icon.name: "ic_fluent_keyboard_20_regular"
            visible: launcherWindow.onSettingsPage
            onTriggered: ConfigManager.requestSettingsSection("hotkeyGroup")
        }
        MenuItem {
            text: qsTr("高级")
            icon.name: "ic_fluent_toolbox_20_regular"
            visible: launcherWindow.onSettingsPage
            onTriggered: ConfigManager.requestSettingsSection("advancedGroup")
        }
        MenuSeparator {
            visible: launcherWindow.onSettingsPage
        }

        MenuItem {
            text: qsTr("快捷操作…")
            icon.name: "ic_fluent_flash_20_regular"
            onTriggered: launcherWindow.openPage("records")
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("重载配置")
            icon.name: "ic_fluent_arrow_sync_20_regular"
            onTriggered: ConfigManager.reloadConfig()
        }
        MenuItem {
            text: qsTr("打开配置目录")
            icon.name: "ic_fluent_folder_open_20_regular"
            onTriggered: ConfigManager.openConfigFolder()
        }
    }

    function popupMoreMenu() {
        // 场景坐标 → 窗口内容坐标；菜单右缘对齐按钮右缘，贴近右边界时再收回来。
        var scene = moreMenuHost.mapToItem(null, moreMenuHost.width, moreMenuHost.height + 4)
        var content = launcherWindow.contentItem
        var local = content.mapFromItem(null, scene.x, scene.y)
        moreMenu.popup(Qt.point(Math.max(0, local.x - moreMenu.width), local.y))
    }

    // ------------------------------------------------------------------
    // 动画总开关：设置里关掉后把 RinUI 的全局动画时长清成 0。
    // ------------------------------------------------------------------
    property var _animDefaults: null

    function applyAnimationSetting() {
        if (launcherWindow._animDefaults === null) {
            // 第一次把 RinUI 的默认值抄下来，之后在默认值和 0 之间来回切。
            launcherWindow._animDefaults = {
                "animationSpeed": Utils.animationSpeed,
                "animationSpeedExpander": Utils.animationSpeedExpander,
                "animationSpeedFaster": Utils.animationSpeedFaster,
                "appearanceSpeed": Utils.appearanceSpeed,
                "animationSpeedMiddle": Utils.animationSpeedMiddle,
                "progressBarAnimationSpeed": Utils.progressBarAnimationSpeed
            }
        }
        var enabled = ConfigManager.getSettings().animationEnabled !== false
        for (var key in launcherWindow._animDefaults) {
            Utils[key] = enabled ? launcherWindow._animDefaults[key] : 0
        }
    }

    Component.onCompleted: launcherWindow.applyAnimationSetting()

    // 后端所有提示都走同一条链路，UI 不必自己维护信息条。
    Connections {
        target: ConfigManager

        function onSettingsChanged() {
            // 动画总开关变化即时生效。
            launcherWindow.applyAnimationSetting()
        }

        function onShowToast(message, severity) {
            launcherWindow.floatLayer.createInfoBar({
                "severity": severity === "success" ? Severity.Success
                    : severity === "warning" ? Severity.Warning
                    : severity === "error" ? Severity.Error
                    : Severity.Info,
                "position": Position.BottomRight,
                "timeout": 3200,
                "closable": true,
                "title": qsTr("提示"),
                "text": message
            })
        }
    }
}
