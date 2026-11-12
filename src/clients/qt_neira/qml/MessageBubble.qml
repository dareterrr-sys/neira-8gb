// MessageBubble.qml — одно сообщение ленты: системное / Нейра / пользователь.
import QtQuick
import QtQuick.Layouts

Item {
    id: mb
    property string role: "assistant"
    property string text: ""
    property string time: ""
    property bool isLast: false
    signal copyRequested(string text)
    signal regenerateRequested()

    implicitHeight: col.implicitHeight + Theme.s3 + Theme.s1

    Column {
        id: col
        y: Theme.s2 - Theme.dp
        width: parent.width
        spacing: 0

        // ---------- системная строка: тихая, по центру ----------
        Item {
            visible: mb.role === "system"
            width: parent.width
            height: visible ? sysPill.height + Theme.s1 : 0

            Text {
                id: sysMeasure
                visible: false
                text: mb.text
                font.family: Theme.fSans
                font.pointSize: Theme.cpt(11.5)
            }
            Rectangle {
                id: sysPill
                anchors.centerIn: parent
                width: Math.min(sysMeasure.implicitWidth + Theme.s5, parent.width - Theme.s6)
                height: sysText.implicitHeight + Theme.s2
                radius: height / 2
                color: Theme.panel
                border.width: Theme.pen
                border.color: Theme.line
                Text {
                    id: sysText
                    anchors.centerIn: parent
                    width: parent.width - Theme.s4
                    text: mb.text
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.cpt(11.5)
                }
            }
        }

        // ---------- Нейра ----------
        Item {
            visible: mb.role === "assistant"
            width: parent.width
            height: visible ? aRow.height + Theme.s2 : 0

            Row {
                id: aRow
                width: parent.width
                spacing: Theme.s3

                Rectangle {
                    width: Theme.px(28); height: width
                    radius: width / 2
                    clip: true
                    color: Theme.raised
                    border.width: Theme.pen
                    border.color: Theme.line2
                    Image {
                        anchors.fill: parent
                        source: brain.appDirUrl + "avatar-round.png"
                        fillMode: Image.PreserveAspectCrop
                        mipmap: true
                        asynchronous: true
                    }
                }

                Column {
                    id: aCol
                    width: Math.min(parent.width - Theme.px(40), 713)
                    spacing: Theme.s1

                    RowLayout {
                        spacing: Theme.s2
                        Text {
                            text: "Нейра"
                            color: Theme.text
                            font.family: Theme.fSans
                            font.pointSize: Theme.cpt(12.5)
                            font.weight: Font.DemiBold
                        }
                        Text {
                            visible: mb.time !== ""
                            text: mb.time
                            color: Theme.text4
                            font.family: Theme.fMono
                            font.pointSize: Theme.cpt(10)
                        }
                    }

                    // вариант b: ответ лежит на карточке с золотой линией слева
                    Item {
                        width: parent.width
                        height: body.height + (Theme.isA ? 0 : Theme.s3)
                        Rectangle {
                            visible: !Theme.isA
                            anchors.fill: parent
                            radius: Theme.rMd
                            color: Theme.panel
                            border.width: Theme.pen
                            border.color: Theme.line
                            Rectangle {
                                width: Theme.px(2)
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.margins: Theme.s2
                                radius: 1
                                color: Theme.accent
                            }
                        }
                        MessageBody {
                            id: body
                            x: Theme.isA ? 0 : Theme.s4
                            y: Theme.isA ? 0 : Theme.s2 + Theme.dp
                            width: parent.width - (Theme.isA ? 0 : Theme.s5)
                            source: mb.text
                            onCopyRequested: (t) => mb.copyRequested(t)
                        }
                    }

                    RowLayout {
                        spacing: Theme.dp
                        MsgAction { kind: "copy"; tip: "Копировать ответ"; onClicked: mb.copyRequested(mb.text) }
                        MsgAction {
                            visible: mb.isLast
                            kind: "refresh"
                            tip: "Ответить заново"
                            onClicked: mb.regenerateRequested()
                        }
                    }
                }
            }
        }

        // ---------- пользователь ----------
        Item {
            visible: mb.role === "user"
            width: parent.width
            height: visible ? uBubble.height + uTime.height + uTime.anchors.topMargin : 0

            Text {
                id: uMeasure
                visible: false
                text: mb.text
                font.family: Theme.fSans
                font.pixelSize: Math.round(14 * Theme.fp)
            }
            Rectangle {
                id: uBubble
                anchors.right: parent.right
                width: Math.min(uMeasure.implicitWidth + 2 * (Theme.s3 + Theme.s1) + Theme.px(6),
                                Math.min(parent.width - Theme.s6, Theme.winWidth >= 2300 ? 552 : 520))
                height: uText.implicitHeight + Theme.s5 - Theme.s1
                radius: Theme.rLg - Theme.dp * 2
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                border.width: Theme.pen
                border.color: Theme.userBorder

                MessageBody {
                    id: uText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: Theme.s3 + Theme.s1
                    anchors.rightMargin: Theme.s3 + Theme.s1
                    anchors.topMargin: Theme.s3 - Theme.dp
                    source: mb.text
                    bodyColor: Theme.text
                    onCopyRequested: (t) => mb.copyRequested(t)
                }
            }
            Text {
                id: uTime
                anchors.right: parent.right
                anchors.top: uBubble.bottom
                anchors.topMargin: Theme.s1
                visible: mb.time !== ""
                text: mb.time
                color: Theme.text4
                font.family: Theme.fMono
                font.pointSize: Theme.pt(9.5)
            }
        }
    }
}
