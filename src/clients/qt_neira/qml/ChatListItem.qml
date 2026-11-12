// ChatListItem.qml — строка разговора в левой панели (клик — открыть, крестик при наведении — удалить).
import QtQuick

Rectangle {
    id: chat
    signal clicked()
    signal removeRequested()
    property string title: ""
    property string sub: ""
    property bool active: false

    radius: Theme.rMd
    color: chat.active ? Theme.accentSoft : (chatArea.containsMouse ? Theme.hover : "transparent")
    Behavior on color { ColorAnimation { duration: Theme.dFast } }

    Rectangle {      // метка активного разговора
        visible: chat.active
        width: Theme.px(2)
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: Theme.s2
        radius: 1
        color: Theme.accent
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: Theme.s3 + Theme.s1
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(32)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.dp * 2
        Text {
            width: parent.width
            text: chat.title
            elide: Text.ElideRight
            color: chat.active ? Theme.text : Theme.text2
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12.5)
            font.weight: Font.DemiBold
        }
        Text {
            width: parent.width
            text: chat.sub
            elide: Text.ElideRight
            color: Theme.text3
            font.family: Theme.fSans
            font.pointSize: Theme.pt(11)
        }
    }

    Item {
        id: delBtn
        visible: chatArea.containsMouse || delArea.containsMouse
        anchors.right: parent.right
        anchors.rightMargin: Theme.s2
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.px(22); height: width
        z: 3
        NIcon {
            anchors.centerIn: parent
            name: "x"
            iconSize: Theme.px(11)
            tint: delArea.containsMouse ? Theme.bad : Theme.text3
        }
        MouseArea {
            id: delArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chat.removeRequested()
        }
    }

    MouseArea {
        id: chatArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chat.clicked()
    }
}
