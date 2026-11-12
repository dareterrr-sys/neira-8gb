// PcControl.qml — окно «Управление ПК» под кнопкой шапки.
// Сообщения сервера (описание — Проект_v3/zrenie-upravlenie/этап1.md):
//   pc-control-status {enabled, reason}   → переключатель и причина (в т.ч. отжатие клавишей Pause)
//   pc-control-action {type, desc}        → лента последних действий
//   pc-control-confirm-request            → карточка PcConfirmCard (в Main поверх всего)
// Пока сервер не прислал ни одного pc-control-*, показывается «недоступно» с причиной, а не тишина.
import QtQuick
import QtQuick.Layouts

Item {
    id: pc
    property bool open: false
    signal closeRequested()

    visible: open
    width: Theme.px(340)
    height: col.implicitHeight + Theme.s5

    Rectangle {
        anchors.fill: parent
        radius: Theme.rLg
        color: Theme.raised
        border.width: 1
        border.color: Theme.line2
    }
    MouseArea { anchors.fill: parent }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.s4
        spacing: Theme.s3

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "Управление ПК"
                color: Theme.text
                font.family: Theme.fSans
                font.pointSize: Theme.pt(13.5)
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
            NeuraSwitch {
                checked: brain.pcEnabled
                enabledSwitch: brain.pcAvailable
                onToggled: brain.pcSetEnabled(!brain.pcEnabled)
            }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12)
            color: !brain.pcAvailable ? Theme.warn : (brain.pcEnabled ? Theme.ok : Theme.text2)
            text: !brain.pcAvailable
                  ? (brain.connectionStatus === "connected"
                     ? "Недоступно: приложение Нейры не сообщает о управлении ПК (сервер без этого органа)."
                     : "Недоступно: нет связи с приложением Нейры.")
                  : (brain.pcEnabled
                     ? "Нейра может двигать мышью и нажимать клавиши. Аварийная остановка — клавиша Pause."
                     : (brain.pcReason !== "" ? "Выключено: " + brain.pcReason
                                              : "Выключено. Включи, чтобы Нейра могла работать с экраном."))
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; visible: actionsCol.visible }

        ColumnLayout {
            id: actionsCol
            visible: brain.pcActions.length > 0
            Layout.fillWidth: true
            spacing: Theme.s1
            Text { text: "Последние действия"; color: Theme.text3; font.family: Theme.fSans
                   font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
            Repeater {
                model: brain.pcActions.slice(-5).reverse()
                delegate: RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.s2
                    Text { text: modelData.time; color: Theme.text4; font.family: Theme.fMono; font.pointSize: Theme.pt(10) }
                    Text {
                        Layout.fillWidth: true
                        text: modelData.desc !== "" ? modelData.desc : modelData.type
                        elide: Text.ElideRight
                        color: Theme.text2
                        font.family: Theme.fSans
                        font.pointSize: Theme.pt(11.5)
                    }
                }
            }
        }
    }
}
