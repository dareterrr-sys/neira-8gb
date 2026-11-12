// HeaderButton.qml — квадратная кнопка-иконка шапки с подсказкой.
import QtQuick

Item {
    id: hb
    property string icon: ""
    property string tip: ""
    property bool on: false              // «нажата»: панель открыта
    signal clicked()

    implicitWidth: Theme.px(32)
    implicitHeight: Theme.px(32)

    Rectangle {
        anchors.fill: parent
        radius: Theme.rMd
        color: hb.on ? Theme.accentSoft : (area.containsMouse ? Theme.hover : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.dFast } }
    }
    NIcon {
        anchors.centerIn: parent
        name: hb.icon
        iconSize: Theme.px(16)
        tint: hb.on ? Theme.accent : (area.containsMouse ? Theme.text : Theme.text3)
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: hb.clicked()
    }
    Rectangle {
        visible: area.containsMouse && hb.tip !== ""
        anchors.top: parent.bottom
        anchors.topMargin: Theme.s1
        anchors.horizontalCenter: parent.horizontalCenter
        width: tipText.implicitWidth + Theme.s3
        height: tipText.implicitHeight + Theme.s2
        radius: Theme.rSm
        color: Theme.raised
        border.width: 1
        border.color: Theme.line2
        z: 50
        Text {
            id: tipText
            anchors.centerIn: parent
            text: hb.tip
            color: Theme.text2
            font.family: Theme.fSans
            font.pointSize: Theme.pt(11)
        }
    }
}
