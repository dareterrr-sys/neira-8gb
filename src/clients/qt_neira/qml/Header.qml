// Header.qml — единая шапка окна: имя и состояние Нейры, связь одной «таблеткой»,
// «Управление ПК», настройки, кнопки окна. Пустое место шапки — перетаскивание окна.
import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes

Item {
    id: hd
    property var win: null
    property string chatTitle: ""
    property string activity: "idle"           // idle | listening | thinking | speaking
    property string stateText: ""
    property bool sidebarOn: true
    property bool stageOn: true
    property bool settingsOn: false
    property bool pcOpen: false
    property bool compact: false               // узкое окно: «Управление ПК» без подписи
    signal sidebarToggled()
    signal stageToggled()
    signal settingsToggled()
    signal pcToggled()

    implicitHeight: Theme.px(52)

    Rectangle { anchors.fill: parent; color: Theme.panel }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }

    MouseArea {
        anchors.fill: parent
        onPressed: (m) => { if (m.button === Qt.LeftButton && hd.win) hd.win.startSystemMove() }
        onDoubleClicked: {
            if (!hd.win) return
            if (hd.win.visibility === Window.Maximized) hd.win.showNormal(); else hd.win.showMaximized()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.s3
        spacing: Theme.s2

        HeaderButton {
            icon: "panel-left"
            tip: Theme.sidebarDocked ? "Панель разговоров" : "Разговоры"
            on: hd.sidebarOn
            onClicked: hd.sidebarToggled()
        }

        // лицо и состояние
        Item {
            Layout.preferredWidth: Theme.px(34)
            Layout.preferredHeight: Theme.px(34)
            Layout.leftMargin: Theme.s1
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                clip: true
                color: Theme.raised
                border.width: Theme.pen
                border.color: hd.activity === "idle" ? Theme.line2 : Theme.accent
                Behavior on border.color { ColorAnimation { duration: Theme.dFast } }
                Image {
                    anchors.fill: parent
                    source: brain.appDirUrl + "avatar-round.png"
                    fillMode: Image.PreserveAspectCrop
                    mipmap: true
                    asynchronous: true
                }
            }
        }
        ColumnLayout {
            spacing: 0
            Text {
                text: "Нейра"
                color: Theme.text
                font.family: Theme.fSans
                font.pointSize: Theme.pt(13.5)
                font.weight: Font.DemiBold
            }
            Text {
                text: hd.stateText
                color: hd.activity === "idle" ? Theme.text3 : Theme.accent
                font.family: Theme.fSans
                font.pointSize: Theme.pt(11)
                SequentialAnimation on opacity {
                    running: hd.activity === "thinking"
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.5; duration: 700; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 0.5; to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
                }
            }
        }

        Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: Theme.px(20); Layout.leftMargin: Theme.s2; color: Theme.line2 }
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.s2
            text: hd.chatTitle
            elide: Text.ElideRight
            color: Theme.text3
            font.family: Theme.fSans
            font.pointSize: Theme.pt(12)
        }

        // ---------- связь: одна таблетка, подробности по наведению ----------
        Rectangle {
            id: pill
            Layout.preferredHeight: Theme.px(28)
            Layout.preferredWidth: dots.width + Theme.s4
            radius: height / 2
            color: pillArea.containsMouse ? Theme.hover : "transparent"
            border.width: 1
            border.color: Theme.line

            Row {
                id: dots
                anchors.centerIn: parent
                spacing: Theme.s2
                Rectangle { width: Theme.px(8); height: width; radius: width / 2
                            color: brain.connectionStatus === "connected" ? Theme.ok
                                 : brain.connectionStatus === "failed" ? Theme.bad : Theme.warn }
                Rectangle { width: Theme.px(8); height: width; radius: width / 2
                            color: brain.brainUp ? Theme.ok : Theme.bad }
                Rectangle { width: Theme.px(8); height: width; radius: width / 2
                            color: !brain.voiceEnabled ? Theme.text4 : (brain.voiceUp ? Theme.ok : Theme.bad) }
            }
            MouseArea { id: pillArea; anchors.fill: parent; hoverEnabled: true }

            Rectangle {      // подробности
                visible: pillArea.containsMouse
                anchors.top: parent.bottom
                anchors.topMargin: Theme.s2
                anchors.right: parent.right
                width: Theme.px(240)
                height: pillCol.implicitHeight + Theme.s4
                radius: Theme.rMd
                color: Theme.raised
                border.width: 1
                border.color: Theme.line2
                z: 60
                ColumnLayout {
                    id: pillCol
                    anchors.fill: parent
                    anchors.margins: Theme.s3
                    spacing: Theme.s2
                    StatusRow { Layout.fillWidth: true; label: "Приложение Нейры"
                        up: brain.connectionStatus === "connected"; okText: "на связи"
                        badText: brain.connectionStatus === "failed" ? "нет связи" : "переподключение…" }
                    StatusRow { Layout.fillWidth: true; label: "Мозг"
                        up: brain.brainUp; okText: "работает"; badText: "не отвечает" }
                    StatusRow { Layout.fillWidth: true; label: "Голос"
                        up: brain.voiceUp; idle: !brain.voiceEnabled; okText: "работает"
                        badText: brain.voiceEnabled ? "не отвечает" : "выключен" }
                }
            }
        }

        // ---------- «Управление ПК» ----------
        Rectangle {
            id: pcBtn
            readonly property bool avail: brain.pcAvailable
            readonly property bool live: brain.pcAvailable && brain.pcEnabled
            Layout.preferredHeight: Theme.px(32)
            Layout.preferredWidth: pcRow.implicitWidth + Theme.s4
            radius: height / 2
            color: live ? Theme.accentSoft : (pcArea.containsMouse || hd.pcOpen ? Theme.hover : "transparent")
            border.width: 1
            border.color: live ? Theme.accent : Theme.line2
            opacity: avail ? 1.0 : 0.8
            Behavior on color { ColorAnimation { duration: Theme.dFast } }

            Row {
                id: pcRow
                anchors.centerIn: parent
                spacing: Theme.s2
                Shape {      // курсор мыши
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.px(14); height: Theme.px(16)
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: pcBtn.live ? Theme.accent : "transparent"
                        strokeColor: pcBtn.live ? Theme.accent : Theme.text3
                        strokeWidth: 1.4 * Theme.dp
                        joinStyle: ShapePath.RoundJoin
                        scale: Qt.size(Theme.dp, Theme.dp)
                        startX: 2; startY: 1
                        PathLine { x: 2; y: 13 }
                        PathLine { x: 5; y: 10 }
                        PathLine { x: 7.5; y: 15 }
                        PathLine { x: 9.5; y: 14 }
                        PathLine { x: 7; y: 9.3 }
                        PathLine { x: 11; y: 9 }
                        PathLine { x: 2; y: 1 }
                    }
                }
                Text {
                    visible: !hd.compact
                    anchors.verticalCenter: parent.verticalCenter
                    text: pcBtn.live ? "Нейра управляет ПК" : "Управление ПК"
                    color: pcBtn.live ? Theme.accent : (pcBtn.avail ? Theme.text2 : Theme.text3)
                    font.family: Theme.fSans
                    font.pointSize: Theme.pt(12)
                }
                Rectangle {   // индикатор: горит — управление включено
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.px(8); height: width; radius: width / 2
                    color: pcBtn.live ? Theme.accent : "transparent"
                    border.width: pcBtn.live ? 0 : 1
                    border.color: pcBtn.avail ? Theme.text3 : Theme.line2
                    SequentialAnimation on opacity {
                        running: pcBtn.live
                        loops: Animation.Infinite
                        NumberAnimation { from: 1.0; to: 0.35; duration: 900; easing.type: Easing.InOutQuad }
                        NumberAnimation { from: 0.35; to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
                    }
                }
            }
            MouseArea {
                id: pcArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: hd.pcToggled()
            }
        }

        HeaderButton { icon: "panel"; tip: "Сцена"; on: hd.stageOn; onClicked: hd.stageToggled() }
        HeaderButton { icon: "sliders"; tip: "Настройки"; on: hd.settingsOn; onClicked: hd.settingsToggled() }

        // ---------- кнопки окна ----------
        Item { Layout.preferredWidth: Theme.s1 }
        Repeater {
            model: [ { ic: "minus", sz: 13, k: "min" }, { ic: "square", sz: 12, k: "max" }, { ic: "x", sz: 13, k: "close" } ]
            delegate: Item {
                Layout.preferredWidth: Theme.px(44)
                Layout.fillHeight: true
                Rectangle {
                    anchors.fill: parent
                    color: wArea.containsMouse ? (modelData.k === "close" ? Theme.badSoft : Theme.hover) : "transparent"
                }
                NIcon {
                    anchors.centerIn: parent
                    name: modelData.ic
                    iconSize: Theme.px(modelData.sz)
                    tint: wArea.containsMouse ? (modelData.k === "close" ? Theme.bad : Theme.text) : Theme.text3
                }
                MouseArea {
                    id: wArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (!hd.win) return
                        if (modelData.k === "min") hd.win.showMinimized()
                        else if (modelData.k === "close") hd.win.close()
                        else if (hd.win.visibility === Window.Maximized) hd.win.showNormal()
                        else hd.win.showMaximized()
                    }
                }
            }
        }
    }
}
