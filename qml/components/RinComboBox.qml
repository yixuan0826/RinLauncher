import QtQuick 2.15
import RinUI

// RinUI 0.5.0 的 ComboBox 用自绘 ContextMenu 实现下拉，Qt Quick Controls 的
// activated 信号永远不会发出去，外部写的 onActivated 就成了死代码。
// 这里把弹出菜单的 itemSelected 转一手，让调用点保持原样。
ComboBox {
    id: root

    Connections {
        target: root.popup

        function onItemSelected(index) {
            root.activated(index)
        }
    }
}
