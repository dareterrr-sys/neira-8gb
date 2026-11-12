// MessageBody.qml — тело сообщения: блоки markdown (абзац / заголовок / список / код).
import QtQuick

Column {
    id: mb
    property string source: ""
    property color bodyColor: Theme.text2
    property int baseSize: 14
    signal copyRequested(string text)

    spacing: Theme.s3 - 2 * Theme.dp

    Repeater {
        model: Markdown.parseBlocks(mb.source)

        delegate: Item {
            id: blockItem
            property var blk: modelData
            width: mb.width
            height: (blk.kind === "ol" || blk.kind === "ul")
                ? listCol.implicitHeight + 2 * Theme.dp
                : (blk.kind === "code" ? codeRect.height : textBlock.implicitHeight)

            Text {
                id: textBlock
                visible: blk.kind === "p" || blk.kind === "h"
                width: parent.width
                textFormat: Text.RichText
                text: Markdown.mdInline(blk.text || "")
                onLinkActivated: (l) => brain.openExternal(l)
                color: blk.kind === "h" ? Theme.text : mb.bodyColor
                linkColor: Theme.lav
                font.family: Theme.fSans
                font.pixelSize: blk.kind === "h"
                    ? Math.round((blk.level === 1 ? 18 : blk.level === 2 ? 16 : 14) * Theme.fp)
                    : Math.round(mb.baseSize * Theme.fp)
                font.weight: blk.kind === "h" ? Font.DemiBold : Font.Normal
                lineHeight: 1.6
                lineHeightMode: Text.ProportionalHeight
                wrapMode: Text.WordWrap
            }

            Column {
                id: listCol
                visible: blk.kind === "ol" || blk.kind === "ul"
                width: parent.width
                spacing: Theme.s1 + Theme.dp * 2

                Repeater {
                    model: blk.items || []
                    delegate: Row {
                        width: listCol.width
                        spacing: Theme.s2

                        Rectangle {
                            visible: blk.kind === "ol"
                            width: Theme.px(18); height: width; radius: Theme.rSm - Theme.dp
                            color: Theme.accentSoft
                            Text {
                                anchors.centerIn: parent
                                text: index + 1
                                color: Theme.accent
                                font.family: Theme.fMono
                                font.pointSize: Theme.pt(9.5)
                            }
                        }
                        Rectangle {
                            visible: blk.kind === "ul"
                            width: Theme.px(5); height: width; radius: width / 2
                            color: Theme.accent
                            anchors.top: parent.top
                            anchors.topMargin: Theme.px(10)
                        }
                        Text {
                            width: parent.width - Theme.px(26)
                            textFormat: Text.RichText
                            text: Markdown.mdInline(modelData)
                            onLinkActivated: (l) => brain.openExternal(l)
                            color: mb.bodyColor
                            linkColor: Theme.lav
                            font.family: Theme.fSans
                            font.pixelSize: Math.round(mb.baseSize * Theme.fp)
                            lineHeight: 1.6
                            lineHeightMode: Text.ProportionalHeight
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Rectangle {
                id: codeRect
                visible: blk.kind === "code"
                width: parent.width
                height: codeText.implicitHeight + Theme.s4
                radius: Theme.rSm
                color: Theme.field
                border.width: 1
                border.color: Theme.line

                MsgAction {
                    z: 2
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.margins: Theme.s1
                    kind: "copy"
                    tip: "Копировать код"
                    onClicked: mb.copyRequested(blk.text || "")
                }
                Text {
                    id: codeText
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    text: blk.text || ""
                    color: Theme.text2
                    font.family: Theme.fMono
                    font.pointSize: Theme.pt(12)
                    wrapMode: Text.NoWrap
                }
            }
        }
    }
}
