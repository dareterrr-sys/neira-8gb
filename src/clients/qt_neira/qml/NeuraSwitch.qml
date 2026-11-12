// NeuraSwitch.qml — переключатель. Состояние задаёт владелец (checked), клик даёт сигнал toggled().
import QtQuick

Rectangle {
    id: sw
    property bool checked: false
    property bool enabledSwitch: true
    signal toggled()

    implicitWidth: Theme.px(38)
    implicitHeight: Theme.px(22)
    radius: height / 2
    opacity: enabledSwitch ? 1.0 : 0.45
    color: checked ? Theme.accentSoft : Theme.field
    border.width: 1
    border.color: checked ? Theme.accent : Theme.line2
    Behavior on color { ColorAnimation { duration: Theme.dFast } }

    Rectangle {
        width: Theme.px(14)
        height: width
        radius: width / 2
        y: (sw.height - height) / 2
        x: sw.checked ? sw.width - width - Theme.px(4) : Theme.px(4)
        color: sw.checked ? Theme.accent : Theme.text4
        Behavior on x { NumberAnimation { duration: Theme.dFast; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent
        enabled: sw.enabledSwitch
        cursorShape: Qt.PointingHandCursor
        onClicked: sw.toggled()
    }
}
