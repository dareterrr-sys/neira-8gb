// ChatView.qml — лента сообщений с прокруткой и кнопкой «в конец».
import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Item {
    id: cv
    property alias model: view.model
    property alias view: view
    signal copyRequested(string text)
    signal regenerateRequested()

    // «Сегодня» / «Вчера» / «10 ноября» (с годом, если год другой); key = "yyyy-MM-dd"
    function dayLabel(key) {
        var p = String(key).split("-")
        if (p.length !== 3) return ""
        var d = new Date(parseInt(p[0]), parseInt(p[1]) - 1, parseInt(p[2]))
        var now = new Date()
        var t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        var diff = Math.round((t0 - d) / 86400000)
        if (diff === 0) return "Сегодня"
        if (diff === 1) return "Вчера"
        var m = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"][d.getMonth()]
        return d.getDate() + " " + m + (d.getFullYear() !== now.getFullYear() ? " " + d.getFullYear() : "")
    }

    function ensureAtBottom() { view.ensureAtBottom() }
    function scrollToBottomNow() { view.scrollToBottomNow() }

    ListView {
        id: view
        anchors.fill: parent
        anchors.topMargin: Theme.s1
        anchors.bottomMargin: Theme.s2
        anchors.leftMargin: Math.max(Theme.px(20), (parent.width - 720 * Theme.fp) / 2)
        anchors.rightMargin: Math.max(Theme.px(20), (parent.width - 720 * Theme.fp) / 2)
        clip: true
        spacing: Theme.dp
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 600

        // Без add: Transition — пока она идёт, ListView не двигает соседей при смене высоты
        // делегата, и в ленте остаётся дыра. Плавное появление — внутри делегата.

        // плашка даты: при смене дня между сообщениями и прилипает сверху при прокрутке
        section.property: "day"
        section.criteria: ViewSection.FullString
        section.labelPositioning: ViewSection.InlineLabels | ViewSection.CurrentLabelAtStart
        section.delegate: Item {
            width: view.width
            height: Theme.px(36)
            Rectangle {
                anchors.centerIn: parent
                width: dayText.implicitWidth + Theme.s5
                height: Theme.px(24)
                radius: height / 2
                color: Theme.raised
                border.width: 1
                border.color: Theme.line
                Text {
                    id: dayText
                    anchors.centerIn: parent
                    text: cv.dayLabel(section)
                    color: Theme.text3
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(11)
                }
            }
        }

        property bool isScrollingUp: false

        Timer {
            id: scrollTimer
            interval: 0
            repeat: false
            onTriggered: {
                view.forceLayout()
                view.positionViewAtEnd()
                Qt.callLater(view.positionViewAtEnd)
            }
        }

        function scrollToBottomNow() {
            isScrollingUp = false
            positionViewAtEnd()
            scrollTimer.start()
        }
        function ensureAtBottom() {
            if (isScrollingUp || moving || flicking) return
            scrollTimer.start()
        }

        onMovementStarted: isScrollingUp = true
        onMovementEnded: isScrollingUp = (contentHeight - contentY) > (height + 50)
        onContentHeightChanged: {
            if (!isScrollingUp && !moving && !flicking) scrollTimer.start()
        }

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
            background: Rectangle { color: "transparent" }
            contentItem: Rectangle { implicitWidth: 4; implicitHeight: 40; radius: 2; color: Theme.line2 }
        }

        delegate: MessageBubble {
            id: del
            width: view.width
            height: implicitHeight
            role: model.role
            text: model.text
            time: model.time
            isLast: index === view.count - 1
            onCopyRequested: (t) => cv.copyRequested(t)
            onRegenerateRequested: cv.regenerateRequested()

            NumberAnimation { id: fadeIn; target: del; property: "opacity"; from: 0; to: 1; duration: Theme.dBase }
            Component.onCompleted: if (index === view.count - 1) fadeIn.start()
        }
    }

    // кнопка «в конец»
    Item {
        width: Theme.px(32)
        height: width
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.s2
        visible: view.isScrollingUp && view.contentHeight > view.height + 8

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Theme.raised
            border.width: Theme.pen
            border.color: downArea.containsMouse ? Theme.accent : Theme.line2
        }
        Shape {
            anchors.centerIn: parent
            width: Theme.px(12); height: Theme.px(12)
            ShapePath {
                strokeColor: downArea.containsMouse ? Theme.text : Theme.text3
                strokeWidth: 1.5 * Theme.dp
                fillColor: "transparent"
                startX: 1; startY: 4
                PathLine { x: 6; y: 9 }
                PathLine { x: 11; y: 4 }
            }
        }
        MouseArea {
            id: downArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: view.scrollToBottomNow()
        }
    }
}
