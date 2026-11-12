// SendButton.qml — кнопка «отправить / остановить». Цвета — только из Theme.
// Геометрия от эталона 30x30: радиус size*7/30, бокс иконки size*18/30, дротик в системе 24x24.
import QtQuick
import QtQuick.Shapes

Item {
    id: ctrl
    property bool generating: false
    property bool canSend: true            // есть что отправлять (текст или вложение)
    property real size: 36
    signal clicked()

    implicitWidth: size
    implicitHeight: size

    readonly property real r: size * 0.5
    readonly property real iconSize: size * 18 / 30
    readonly property real u: iconSize / 24
    readonly property real stopSide: size * 11 / 30
    readonly property bool hovered: mouse.containsMouse
    readonly property bool active: generating || canSend

    scale: mouse.pressed ? 0.96 : 1.0
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.InOutQuad } }

    Rectangle {
        anchors.fill: parent
        radius: ctrl.r
        color: ctrl.generating ? (ctrl.hovered ? Theme.bad : Theme.raised)
             : ctrl.canSend ? (ctrl.hovered ? Theme.text : Theme.accent)
             : Theme.raised
        border.width: ctrl.generating ? Theme.pen : 0
        border.color: Theme.bad
        Behavior on color { ColorAnimation { duration: Theme.dFast } }
    }

    // дротик
    Shape {
        anchors.centerIn: parent
        width: ctrl.iconSize
        height: ctrl.iconSize
        visible: !ctrl.generating
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: ctrl.canSend ? Theme.accentText : Theme.text4
            strokeColor: "transparent"
            strokeWidth: 0
            joinStyle: ShapePath.MiterJoin
            startX: 12.0 * ctrl.u
            startY: 3.75 * ctrl.u
            PathLine { x: 20.8 * ctrl.u; y: 20.25 * ctrl.u }
            PathLine { x: 12.0 * ctrl.u; y: 15.45 * ctrl.u }
            PathLine { x: 3.2 * ctrl.u; y: 20.25 * ctrl.u }
            PathLine { x: 12.0 * ctrl.u; y: 3.75 * ctrl.u }
        }
    }

    // квадрат стопа
    Rectangle {
        anchors.centerIn: parent
        width: ctrl.stopSide
        height: width
        radius: width * 0.18
        visible: ctrl.generating
        color: ctrl.hovered ? Theme.accentText : Theme.bad
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: ctrl.clicked()
    }
}
