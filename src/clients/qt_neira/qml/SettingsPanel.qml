// SettingsPanel.qml — выезжающие настройки справа. Две вкладки:
//   «Нейра»   — голос, озвучка, предлагать темы, память;
//   «Система» — связь, мозг, скорость, лог. Параметров генерации нет (ими управляют сервер и совет).
import QtQuick
import QtQuick.Layouts

Item {
    id: sp
    property bool open: false
    property int tab: 0
    signal closeRequested()
    signal topicRequested()

    visible: x < parent.width
    width: Theme.px(344)
    x: open ? parent.width - width : parent.width
    Behavior on x { NumberAnimation { duration: Theme.dBase; easing.type: Easing.OutCubic } }

    Rectangle { anchors.fill: parent; color: Theme.panel }
    Rectangle { anchors.left: parent.left; width: 1; height: parent.height; color: Theme.line2 }
    MouseArea { anchors.fill: parent }       // не пропускать клики на ленту под панелью

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // шапка + вкладки
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(52)
            Text {
                anchors.left: parent.left
                anchors.leftMargin: Theme.s4
                anchors.verticalCenter: parent.verticalCenter
                text: "Настройки"
                color: Theme.text
                font.family: Theme.fSans
                font.pointSize: Theme.pt(14)
                font.weight: Font.DemiBold
            }
            HeaderButton {
                anchors.right: parent.right
                anchors.rightMargin: Theme.s3
                anchors.verticalCenter: parent.verticalCenter
                icon: "x"
                tip: "Закрыть"
                onClicked: sp.closeRequested()
            }
        }
        Row {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.s4
            spacing: Theme.s4
            Repeater {
                model: ["Нейра", "Система"]
                delegate: Item {
                    width: tabText.implicitWidth
                    height: Theme.px(34)
                    Text {
                        id: tabText
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData
                        color: sp.tab === index ? Theme.text : Theme.text3
                        font.family: Theme.fSans
                        font.pointSize: Theme.pt(12.5)
                        font.weight: sp.tab === index ? Font.DemiBold : Font.Normal
                    }
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: Theme.px(2)
                        color: sp.tab === index ? Theme.accent : "transparent"
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: sp.tab = index
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        // ---------- вкладка «Нейра» ----------
        ColumnLayout {
            visible: sp.tab === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.s4
            spacing: Theme.s5

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s3
                Text { text: "Голос"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Озвучивать ответы"
                        color: Theme.text2
                        font.family: Theme.fSans
                        font.pointSize: Theme.pt(12.5)
                    }
                    Item { Layout.fillWidth: true }
                    NeuraSwitch { checked: brain.voiceEnabled; onToggled: brain.toggleVoice() }
                }
                Text {
                    Layout.fillWidth: true
                    text: brain.voiceEnabled ? (brain.voiceUp ? "Голос работает." : "Голос включён, но сервер голоса не отвечает.")
                                             : "Нейра отвечает только текстом."
                    wrapMode: Text.WordWrap
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(11.5)
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s3
                Text { text: "Инициатива"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(36)
                    radius: Theme.rMd
                    color: topicArea.containsMouse && !brain.isGenerating ? Theme.hover : "transparent"
                    border.width: 1
                    border.color: Theme.line2
                    opacity: brain.isGenerating ? 0.5 : 1.0
                    Text {
                        anchors.centerIn: parent
                        text: "Пусть Нейра предложит тему"
                        color: Theme.text
                        font.family: Theme.fSans
                        font.pointSize: Theme.pt(12.5)
                    }
                    MouseArea {
                        id: topicArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: if (!brain.isGenerating) sp.topicRequested()
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s2
                Text { text: "Память"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                Text {
                    Layout.fillWidth: true
                    text: "Нейра помнит открытый разговор. Память фактов включается при запуске сервера (NEIRA_MEMORY), отсюда не переключается."
                    wrapMode: Text.WordWrap
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(11.5)
                }
            }
            Item { Layout.fillHeight: true }
        }

        // ---------- вкладка «Система» ----------
        ColumnLayout {
            visible: sp.tab === 1
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.s4
            spacing: Theme.s5

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s3
                Text { text: "Связь"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                StatusRow { Layout.fillWidth: true; label: "Приложение Нейры"
                    up: brain.connectionStatus === "connected"; okText: "на связи"
                    badText: brain.connectionStatus === "failed" ? "нет связи" : "переподключение…" }
                StatusRow { Layout.fillWidth: true; label: "Мозг"; up: brain.brainUp; okText: "работает"; badText: "не отвечает" }
                StatusRow { Layout.fillWidth: true; label: "Голос"; up: brain.voiceUp; idle: !brain.voiceEnabled
                    okText: "работает"; badText: brain.voiceEnabled ? "не отвечает" : "выключен" }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s3
                Text { text: "Скорость"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "Последний ответ"; color: Theme.text2; font.family: Theme.fSans; font.pointSize: Theme.pt(12.5) }
                    Item { Layout.fillWidth: true }
                    Text { text: brain.speed; color: Theme.text; font.family: Theme.fSans; font.pointSize: Theme.pt(12) }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "Токенов в разговоре"; color: Theme.text2; font.family: Theme.fSans; font.pointSize: Theme.pt(12.5) }
                    Item { Layout.fillWidth: true }
                    Text { text: brain.ctxTokens >= 0 ? String(brain.ctxTokens) : "—"; color: Theme.text; font.family: Theme.fMono; font.pointSize: Theme.pt(11.5) }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.s2
                Text { text: "Журнал"; color: Theme.text3; font.family: Theme.fSans; font.pointSize: Theme.pt(11); font.weight: Font.DemiBold }
                Text {
                    Layout.fillWidth: true
                    text: "neira_qt.log — рядом с neira_qt.exe, до 5 МБ (старый — neira_qt.log.1)."
                    wrapMode: Text.WordWrap
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(11.5)
                }
            }
            Item { Layout.fillHeight: true }
        }
    }
}
