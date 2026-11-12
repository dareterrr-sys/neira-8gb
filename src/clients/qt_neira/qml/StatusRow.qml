// StatusRow.qml — строка «служба: состояние» с точкой (только индикация, не кнопка).
import QtQuick
import QtQuick.Layouts

RowLayout {
    property string label: ""
    property bool up: false
    property bool idle: false          // служба выключена намеренно (не ошибка)
    property string okText: ""
    property string badText: ""
    spacing: Theme.s2

    Text {
        text: parent.label
        color: Theme.text2
        font.family: Theme.fSans
        font.pointSize: Theme.pt(12)
    }
    Item { Layout.fillWidth: true }
    Rectangle {
        width: Theme.px(8); height: width; radius: width / 2
        color: parent.up ? Theme.ok : (parent.idle ? Theme.text4 : Theme.warn)
    }
    Text {
        text: parent.up ? parent.okText : parent.badText
        color: parent.up ? Theme.ok : (parent.idle ? Theme.text3 : Theme.warn)
        font.family: Theme.fSans
        font.pointSize: Theme.pt(11.5)
    }
}
