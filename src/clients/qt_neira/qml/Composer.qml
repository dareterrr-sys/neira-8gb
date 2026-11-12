// Composer.qml — поле ввода: вложения, микрофон, отправка и одна строка статуса.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: cp
    property var win: null                    // окно (для «снимка экрана»: его надо свернуть)
    property alias input: input
    signal sendRequested(string text)
    signal stopRequested()

    implicitHeight: col.implicitHeight + Theme.s3

    function focusInput() { input.forceActiveFocus() }
    function submit() {
        var t = input.text
        if (t.trim() === "" && brain.attachments.length === 0) return
        input.text = ""
        cp.sendRequested(t)
    }

    // снимок экрана: сначала сворачиваем своё окно, чтобы оно не закрывало экран
    Timer {
        id: shotTimer
        interval: 450
        repeat: false
        property bool phase2: false
        onTriggered: {
            if (!phase2) {
                phase2 = true
                if (cp.win) cp.win.showMinimized()
                interval = 600
                start()
            } else {
                phase2 = false
                interval = 450
                brain.attachScreenshot()
                if (cp.win) { cp.win.showNormal(); cp.win.requestActivate() }
            }
        }
        function startSequence() { phase2 = false; interval = 450; start() }
    }

    Column {
        id: col
        width: parent.width
        spacing: Theme.s2

        // вложения
        Row {
            x: (parent.width - Theme.colW(parent.width)) / 2
            spacing: Theme.s2
            visible: brain.attachments.length > 0
            Repeater {
                model: brain.attachments
                delegate: Rectangle {
                    height: Theme.px(26)
                    width: chipText.implicitWidth + Theme.px(40)
                    radius: height / 2
                    color: Theme.accentSoft
                    border.width: 1
                    border.color: Theme.line2
                    Text {
                        id: chipText
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.s3
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData
                        color: Theme.text2
                        font.family: Theme.fSans
                        font.pointSize: Theme.pt(11)
                    }
                    NIcon {
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.s2
                        anchors.verticalCenter: parent.verticalCenter
                        name: "x"
                        iconSize: Theme.px(10)
                        tint: chipX.containsMouse ? Theme.text : Theme.text3
                    }
                    MouseArea {
                        id: chipX
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: Theme.px(28)
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: brain.removeAttachment(index)
                    }
                }
            }
        }

        // поле
        Rectangle {
            id: shell
            x: (parent.width - width) / 2
            width: Theme.colW(parent.width)
            height: Theme.px(88)
            radius: Theme.isA ? Theme.rLg : Theme.px(26)
            color: Theme.field
            border.width: Theme.pen
            border.color: input.activeFocus ? Theme.accent : Theme.line2
            Behavior on border.color { ColorAnimation { duration: Theme.dFast } }

            ScrollView {
                id: inputScroll
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.s4
                anchors.rightMargin: Theme.s4
                anchors.topMargin: Theme.s3
                height: Theme.px(40)
                clip: true
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                TextArea {
                    id: input
                    width: inputScroll.availableWidth
                    color: Theme.text
                    selectionColor: Theme.iris
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(14)
                    placeholderText: brain.recording ? "Идёт запись… нажми микрофон ещё раз — отправлю" : "Написать Нейре…"
                    placeholderTextColor: Theme.text4
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    topPadding: 0
                    bottomPadding: 0
                    background: Rectangle { color: "transparent" }

                    Keys.onReturnPressed: (event) => {
                        if (event.modifiers & Qt.ShiftModifier) { event.accepted = false; return }
                        event.accepted = true
                        cp.submit()
                    }
                    Keys.onEscapePressed: input.text = ""
                }
            }

            RowLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: Theme.s2
                anchors.rightMargin: Theme.s2
                anchors.bottomMargin: Theme.s2
                spacing: Theme.s1

                // прикрепить: картинка из файла или снимок экрана
                Item {
                    Layout.preferredWidth: Theme.px(30)
                    Layout.preferredHeight: Theme.px(30)
                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.rSm
                        color: attachArea.containsMouse || attachMenu.visible ? Theme.hover : "transparent"
                    }
                    NIcon {
                        anchors.centerIn: parent
                        name: "paperclip"
                        iconSize: Theme.px(16)
                        tint: attachArea.containsMouse || brain.attachments.length > 0 ? Theme.accent : Theme.text3
                    }
                    MouseArea {
                        id: attachArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: attachMenu.open()
                    }
                    Popup {
                        id: attachMenu
                        parent: attachArea
                        x: 0
                        y: -height - Theme.s2
                        width: Theme.px(220)
                        padding: Theme.s1
                        background: Rectangle {
                            color: Theme.raised
                            radius: Theme.rMd
                            border.width: 1
                            border.color: Theme.line2
                        }
                        Column {
                            width: attachMenu.availableWidth
                            spacing: 2
                            Repeater {
                                model: [
                                    { key: "file", label: "Картинка из файла…" },
                                    { key: "shot", label: "Снимок экрана" }
                                ]
                                delegate: Rectangle {
                                    width: parent.width
                                    height: Theme.px(32)
                                    radius: Theme.rSm
                                    color: itemArea.containsMouse ? Theme.hover : "transparent"
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: Theme.s3
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.label
                                        color: Theme.text2
                                        font.family: Theme.fSans
                                        font.pointSize: Theme.pt(12)
                                    }
                                    MouseArea {
                                        id: itemArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            attachMenu.close()
                                            if (modelData.key === "file") brain.attachImage()
                                            else shotTimer.startSequence()
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // голосовой ввод: нажал — говоришь, нажал снова — отправка
                Item {
                    Layout.preferredWidth: Theme.px(30)
                    Layout.preferredHeight: Theme.px(30)
                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.rSm
                        color: brain.recording ? Theme.badSoft
                             : micArea.containsMouse ? Theme.hover : "transparent"
                        border.width: brain.recording ? 1 : 0
                        border.color: Theme.bad
                    }
                    NIcon {
                        anchors.centerIn: parent
                        name: "mic"
                        iconSize: Theme.px(16)
                        tint: brain.recording ? Theme.bad : (micArea.containsMouse ? Theme.accent : Theme.text3)
                    }
                    MouseArea {
                        id: micArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: brain.toggleMic()
                    }
                }

                Item { Layout.fillWidth: true }

                SendButton {
                    size: Theme.px(34)
                    generating: brain.isGenerating
                    canSend: input.text.trim() !== "" || brain.attachments.length > 0
                    onClicked: {
                        if (brain.isGenerating) cp.stopRequested()
                        else cp.submit()
                    }
                }
            }
        }

        // одна строка статуса: скорость · токены · голос
        Item {
            x: shell.x
            width: shell.width
            height: Theme.px(18)
            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.s2
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.px(6); height: width; radius: width / 2
                    color: brain.isGenerating ? Theme.accent : (brain.connectionStatus === "connected" ? Theme.ok : Theme.warn)
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(11)
                    text: (brain.speed !== "—" && brain.speed !== "" ? brain.speed + "  ·  " : "")
                          // «≈N ток.» убрано 11.11 (приёмка): число считал клиент по символам, не совпадало с замером мозга
                          + "голос " + (brain.voiceEnabled ? "включён" : "выключен")
                }
            }
        }
        Item { width: 1; height: Theme.s1 }
    }
}
