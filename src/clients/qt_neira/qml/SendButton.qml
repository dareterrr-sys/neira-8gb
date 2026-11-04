// SendButton.qml — кнопка отправки «Нейры».
//
// Геометрия построена от эталона 30×30 (мой прототип) и масштабируется
// пропорционально через size. Ничего не подгоняется на глаз:
//   радиус плашки   = size * 7/30   (23 %)
//   бокс иконки     = size * 18/30  (60 %)
//   глиф дротика    = 17.6 × 16.5 в системе 24×24, симметричен по x = 12
//   квадрат стопа   = size * 11/30  (37 %)
//
// Дротик задан в системе координат 24×24, поэтому центрируется
// математически: bbox-центр пути ровно (12, 12).
//
// Использование в Main.qml:
//   SendButton {
//       id: sendBtn
//       size: 44
//       generating: brain.isGenerating
//       onClicked: {
//           if (brain.isGenerating) {
//               brain.stop(); root.isThinking = false; root.isPrinting = false
//           } else {
//               root.send()
//           }
//       }
//   }

import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: ctrl

    // ---------- API ----------
    property bool generating: false
    property real size: 44
    property real strokeWidth: 1
    signal clicked()

    implicitWidth: size
    implicitHeight: size

    // ---------- геометрия (проценты от эталона 30 px) ----------
    readonly property real r:         size * 7  / 30
    readonly property real iconSize:  size * 18 / 30
    readonly property real u:         iconSize / 24      // шаг системы дротика
    readonly property real stopSide:  size * 11 / 30

    // ---------- палитра ----------
    readonly property color clrBlue:       "#009EFF"
    readonly property color clrOrange:     "#FF6C00"
    readonly property color clrIndigo:     "#5B7CFF"
    readonly property color clrBorderIdle: "#2A3F6B"
    readonly property color clrStopBorder: "#6E2A3A"
    readonly property color clrStopHover:  "#FF5C7A"
    readonly property color clrWhite:      "#FFFFFF"

    readonly property bool hovered: mouse.containsMouse

    scale: mouse.pressed ? 0.96 : 1.0
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.InOutQuad } }

    // ---------- пластина: покой ----------
    Rectangle {
        anchors.fill: parent
        radius: ctrl.r
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#111A29" }
            GradientStop { position: 1.0; color: "#0B1320" }
        }
    }

    // ---------- пластина: наведение (пуск) ----------
    Rectangle {
        anchors.fill: parent
        radius: ctrl.r
        opacity: (ctrl.hovered && !ctrl.generating) ? 1.0 : 0.0
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#152036" }
            GradientStop { position: 1.0; color: "#0E1726" }
        }
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.InOutQuad } }
    }

    // ---------- пластина: стоп ----------
    Rectangle {
        anchors.fill: parent
        radius: ctrl.r
        opacity: ctrl.generating ? 1.0 : 0.0
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1F1620" }
            GradientStop { position: 1.0; color: "#150F17" }
        }
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.InOutQuad } }
    }

    // ---------- рамка + свечение ----------
    Rectangle {
        anchors.fill: parent
        radius: ctrl.r
        color: "transparent"
        border.width: ctrl.strokeWidth
        border.color: ctrl.generating
            ? (ctrl.hovered ? ctrl.clrStopHover : ctrl.clrStopBorder)
            : (ctrl.hovered ? ctrl.clrIndigo   : ctrl.clrBorderIdle)
        Behavior on border.color { ColorAnimation { duration: 160; easing.type: Easing.InOutQuad } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: ctrl.generating
                ? (ctrl.hovered ? "#FF6C00" : "#FF5C7A")
                : (ctrl.hovered ? "#009EFF" : "#5A82FF")
            shadowBlur: ctrl.hovered ? 0.60 : 0.16
            shadowVerticalOffset: 0
            shadowHorizontalOffset: 0
            shadowScale: 1.0
            opacity: ctrl.hovered ? 0.95 : 0.15
            Behavior on shadowBlur { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }
            Behavior on opacity    { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }
        }
    }

    // ---------- дротик ----------
    Shape {
        anchors.centerIn: parent
        width: ctrl.iconSize
        height: ctrl.iconSize
        visible: !ctrl.generating
        // без MSAA у окна antialiasing у Shape не работает — края «лесенкой»;
        // CurveRenderer сглаживает сам
        preferredRendererType: Shape.CurveRenderer

        // свечение только при наведении — в покое белый остаётся белым
        layer.enabled: ctrl.hovered
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#009EFF"
            shadowBlur: 0.60
            shadowVerticalOffset: 0
            shadowHorizontalOffset: 0
            shadowScale: 1.0
            opacity: 0.95
        }

        ShapePath {
            fillColor: ctrl.hovered ? ctrl.clrBlue : ctrl.clrWhite
            strokeColor: "transparent"
            strokeWidth: 0
            capStyle: ShapePath.FlatCap
            joinStyle: ShapePath.MiterJoin

            startX: 12.0 * ctrl.u
            startY: 3.75 * ctrl.u
            PathLine { x: 20.8 * ctrl.u; y: 20.25 * ctrl.u }
            PathLine { x: 12.0 * ctrl.u; y: 15.45 * ctrl.u }
            PathLine { x: 3.2  * ctrl.u; y: 20.25 * ctrl.u }
            PathLine { x: 12.0 * ctrl.u; y: 3.75  * ctrl.u }

            Behavior on fillColor { ColorAnimation { duration: 160; easing.type: Easing.InOutQuad } }
        }
    }

    // ---------- квадрат стопа ----------
    Rectangle {
        anchors.centerIn: parent
        width: ctrl.stopSide
        height: ctrl.stopSide
        radius: ctrl.stopSide * 0.18
        visible: ctrl.generating
        color: ctrl.hovered ? ctrl.clrOrange : ctrl.clrWhite
        Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.InOutQuad } }

        layer.enabled: ctrl.hovered
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#FF6C00"
            shadowBlur: 0.60
            shadowVerticalOffset: 0
            shadowHorizontalOffset: 0
            shadowScale: 1.0
            opacity: 0.95
        }
    }

    // ---------- ввод ----------
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: ctrl.clicked()
    }
}
