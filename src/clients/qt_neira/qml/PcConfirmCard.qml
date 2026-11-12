// PcConfirmCard.qml — карточка «Разрешить действие?» (pc-control-confirm-request → pc-control-confirm {id, ok}).
// Сервер ждёт ответ с тайм-аутом (по тайм-ауту — отказ), поэтому карточка видна поверх всего.
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: card
    readonly property bool shown: brain.pcConfirm.id !== undefined && String(brain.pcConfirm.id) !== ""
    visible: shown
    width: Theme.px(420)
    height: col.implicitHeight + Theme.s5
    radius: Theme.rLg
    color: Theme.raised
    border.width: Theme.pen
    border.color: Theme.accent

    MouseArea { anchors.fill: parent }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.s4
        spacing: Theme.s2

        Text {
            text: "Нейра просит разрешения"
            color: Theme.accent
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12)
            font.weight: Font.DemiBold
        }
        Text {
            Layout.fillWidth: true
            text: brain.pcConfirm.action !== undefined ? String(brain.pcConfirm.action) : ""
            wrapMode: Text.WordWrap
            color: Theme.text
            font.family: Theme.fSans
            font.pointSize: Theme.pt(14)
        }
        Text {
            Layout.fillWidth: true
            visible: brain.pcConfirm.reason !== undefined && String(brain.pcConfirm.reason) !== ""
            text: brain.pcConfirm.reason !== undefined ? String(brain.pcConfirm.reason) : ""
            wrapMode: Text.WordWrap
            color: Theme.text3
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12)
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.s1
            spacing: Theme.s2
            Item { Layout.fillWidth: true }
            Rectangle {
                Layout.preferredHeight: Theme.px(34)
                Layout.preferredWidth: Theme.px(100)
                radius: Theme.rMd
                color: noArea.containsMouse ? Theme.hover : "transparent"
                border.width: 1
                border.color: Theme.line2
                Text { anchors.centerIn: parent; text: "Отказать"; color: Theme.text2
                       font.family: Theme.fSans; font.pointSize: Theme.pt(12.5) }
                MouseArea { id: noArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: brain.pcAnswer(String(brain.pcConfirm.id), false) }
            }
            Rectangle {
                Layout.preferredHeight: Theme.px(34)
                Layout.preferredWidth: Theme.px(110)
                radius: Theme.rMd
                color: yesArea.containsMouse ? Theme.text : Theme.accent
                Text { anchors.centerIn: parent; text: "Разрешить"; color: Theme.accentText
                       font.family: Theme.fSans; font.pointSize: Theme.pt(12.5); font.weight: Font.DemiBold }
                MouseArea { id: yesArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: brain.pcAnswer(String(brain.pcConfirm.id), true) }
            }
        }
    }
}
