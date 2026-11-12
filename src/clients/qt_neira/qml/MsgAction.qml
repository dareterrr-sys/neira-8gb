// MsgAction.qml — маленькая кнопка-иконка под ответом (копировать, повторить).
import QtQuick

Item {
    id: act
    property string kind: ""
    property string tip: ""
    signal clicked()

    implicitWidth: Theme.px(26)
    implicitHeight: Theme.px(26)

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        color: actArea.containsMouse ? Theme.hover : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.dFast } }
    }
    NIcon {
        anchors.centerIn: parent
        name: act.kind
        iconSize: Theme.px(14)
        tint: actArea.containsMouse ? Theme.text : Theme.text3
    }
    MouseArea {
        id: actArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: act.clicked()
    }
    Rectangle {      // подсказка по наведению
        visible: actArea.containsMouse && act.tip !== ""
        anchors.bottom: parent.top
        anchors.bottomMargin: Theme.s1
        anchors.horizontalCenter: parent.horizontalCenter
        width: tipText.implicitWidth + Theme.s3
        height: tipText.implicitHeight + Theme.s2
        radius: Theme.rSm
        color: Theme.raised
        border.width: 1
        border.color: Theme.line2
        z: 20
        Text {
            id: tipText
            anchors.centerIn: parent
            text: act.tip
            color: Theme.text2
            font.family: Theme.fSans
            font.pointSize: Theme.pt(11)
        }
    }
}
