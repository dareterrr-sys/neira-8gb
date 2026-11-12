// Sidebar.qml — разговоры из серверной истории: новый, поиск, список, удаление.
import QtQuick
import QtQuick.Layouts

Item {
    id: sb
    property var sessions: null              // ListModel {uid, title, sub}
    property string activeUid: ""
    signal newChatRequested()
    signal openRequested(string uid, string title)
    signal removeRequested(string uid)
    signal filterChanged(string text)

    function focusSearch() { searchField.forceActiveFocus() }

    Rectangle { anchors.fill: parent; color: Theme.rail }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.line }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s3
        spacing: Theme.s3

        // новый разговор — единственная заливка на панели
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(40)
            radius: Theme.rMd
            gradient: Gradient {      // тот же серебристый градиент, что был у кнопки до редизайна
                GradientStop { position: 0.0; color: newArea.containsMouse ? "#F4F8FF" : Theme.accentHi }
                GradientStop { position: 1.0; color: newArea.containsMouse ? "#D3E4FB" : Theme.accent }
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.s3 + Theme.s1
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.s2
                NIcon { anchors.verticalCenter: parent.verticalCenter; name: "plus"; iconSize: Theme.px(13); tint: Theme.accentText }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Новый разговор"
                    color: Theme.accentText
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(12.5)
                    font.weight: Font.DemiBold
                }
            }
            Text {
                anchors.right: parent.right
                anchors.rightMargin: Theme.s3 + Theme.s1
                anchors.verticalCenter: parent.verticalCenter
                text: "Ctrl N"
                color: Theme.accentText
                opacity: 0.7
                font.family: Theme.fMono
                font.pointSize: Theme.pt(9.5)
            }
            MouseArea {
                id: newArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: sb.newChatRequested()
            }
        }

        // поиск
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(34)
            radius: Theme.rMd
            color: Theme.field
            border.width: 1
            border.color: searchField.activeFocus ? Theme.accent : Theme.line

            NIcon {
                x: Theme.s3
                anchors.verticalCenter: parent.verticalCenter
                name: "search"
                iconSize: Theme.px(13)
                tint: Theme.text4
            }
            TextInput {
                id: searchField
                anchors.fill: parent
                anchors.leftMargin: Theme.px(34)
                anchors.rightMargin: Theme.s3
                verticalAlignment: TextInput.AlignVCenter
                color: Theme.text
                font.family: Theme.fSans
                font.pointSize: Theme.pt(12)
                selectByMouse: true
                clip: true
                onTextChanged: sb.filterChanged(text)
            }
            Text {
                anchors.left: parent.left
                anchors.leftMargin: Theme.px(34)
                anchors.verticalCenter: parent.verticalCenter
                visible: searchField.text === ""
                text: "Поиск по разговорам"
                color: Theme.text4
                font.family: Theme.fSans
                font.pointSize: Theme.pt(12)
            }
        }

        Text {
            Layout.topMargin: Theme.s1
            text: "Разговоры"
            color: Theme.text3
            font.family: Theme.fSans
            font.pointSize: Theme.pt(11)
            font.weight: Font.DemiBold
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.dp * 2
            model: sb.sessions
            clip: true
            delegate: ChatListItem {
                width: list.width
                height: Theme.px(48)
                title: model.title
                sub: model.sub
                active: model.uid === sb.activeUid
                onClicked: sb.openRequested(model.uid, model.title)
                onRemoveRequested: sb.removeRequested(model.uid)
            }

            Text {
                anchors.centerIn: parent
                visible: list.count === 0
                text: searchField.text === "" ? "Пока нет разговоров" : "Ничего не найдено"
                color: Theme.text4
                font.family: Theme.fSans
                font.pointSize: Theme.pt(12)
            }
        }
    }
}
