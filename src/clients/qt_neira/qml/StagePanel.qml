// StagePanel.qml — сцена: место под анимированную Нейру (NeiraAvatar) и подпись состояния.
import QtQuick

Item {
    id: sp
    property string state: "idle"
    property real mouthLevel: 0
    property string emotion: "neutral"
    property bool still: false
    property real baseTilt: 0
    property real swayFix: 99
    property string poseFix: ""
    property real stress: 0
    property real flashFix: -1
    property real flashTime: 0.37
    property real blinkFix: 99
    property string stateText: ""
    clip: true

    Rectangle { anchors.fill: parent; color: Theme.bg }

    NeiraAvatar {
        anchors.fill: parent
        state: sp.state
        mouthLevel: sp.mouthLevel
        emotion: sp.emotion
        still: sp.still
        baseTilt: sp.baseTilt
        swayFix: sp.swayFix
        blinkFix: sp.blinkFix
        poseFix: sp.poseFix
        stress: sp.stress
        flashFix: sp.flashFix
        flashTime: sp.flashTime
    }

    // граница со стороны чата
    Rectangle {
        anchors.left: Theme.stageLeft ? undefined : parent.left
        anchors.right: Theme.stageLeft ? parent.right : undefined
        width: Theme.pen
        height: parent.height
        z: 3
        color: Theme.line
    }

    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: Theme.s5
        spacing: Theme.s2
        visible: sp.width > Theme.px(120)
        Text {
            text: "Нейра"
            color: Theme.text
            font.family: Theme.fSans
            font.pointSize: Theme.pt(14)
            font.weight: Font.DemiBold
        }
        Text {
            anchors.baseline: parent.children[0].baseline
            text: sp.stateText !== "" ? "· " + sp.stateText : ""
            color: Theme.text3
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12)
        }
    }
}
