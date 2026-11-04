// Main.qml — интерфейс Нейры по чертежу DEMO.
// Логика — существующий NeiraBrain (context property "brain").
// Нативный заголовок окна оставлен как есть; кастомный тайтбар — следующий шаг.

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Effects

Window {
    id: root

    width: 1280
    height: 820
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "Нейра — чат"
    color: root.cBg
    flags: Qt.Window | Qt.FramelessWindowHint

    // ============================================================
    // МАСШТАБ: геометрия растёт быстрее шрифтов
    // ============================================================
    readonly property real dp: width >= 2300 ? 1.25 : (width >= 1900 ? 1.08 : 1.0)
    readonly property real fp: 1.0 + (dp - 1.0) * 0.6
    readonly property real pen: dp >= 1.2 ? 1.2 : 1.0

    // ============================================================
    // ПАЛИТРА
    // ============================================================
    readonly property color cBg:      "#04070e"
    readonly property color cRail:    "#070b13"
    readonly property color cPanel:   "#0a0e17"
    readonly property color cLine:    Qt.rgba(0.59, 0.72, 0.89, 0.10)
    readonly property color cLine2:   Qt.rgba(0.59, 0.72, 0.89, 0.20)
    readonly property color cText:    "#E8EEF8"
    readonly property color cText2:   "#A3B2C7"
    readonly property color cText3:   "#74869E"
    readonly property color cText4:   "#5E7086"
    readonly property color cBody:    "#CBD7E6"
    readonly property color cIce:     "#D9E7FF"
    readonly property color cIce2:    "#AAC7EF"
    readonly property color cBlue:    "#6E9BD4"
    readonly property color cOk:      "#6FE3C1"
    readonly property color cBad:     "#F0999F"
    readonly property color cWarn:    "#FFB020"
    readonly property color cSys:     "#FF8A3D"

    readonly property string fSans: "Segoe UI"
    readonly property string fMono: "Cascadia Code"

    readonly property string artSource: "file:///D:/AI/neira-tools/qt_neira/art.png"
    readonly property string avatarSource: "file:///D:/AI/neira-tools/qt_neira/avatar-round.png"
    readonly property rect avatarCrop: Qt.rect(1900, 210, 380, 380)

    // ============================================================
    // СОСТОЯНИЕ UI
    // ============================================================
    property bool isThinking: false
    property bool isPrinting: false
    property bool railOn: true
    property bool stageOn: true
    property bool paramsOpen: false
    property int activeChat: 0
    property string chatTitle: "Дизайн чата"
    property string statusOverride: ""
    property bool voicePlaying: false
    property bool recording: false
    property bool stubVoice: true
    property bool stubMemory: true
    property bool stubTopics: false
    property string stubModel: "Mistral 7B Instruct"
    property string stubVoiceTone: "Нейра — мягкий"
    property real mainRightPad: (paramsOpen && !stageShown) ? 304 * dp : 0
    Behavior on mainRightPad { NumberAnimation { duration: 300; easing.type: Easing.InOutCubic } }

    readonly property bool railShown: railOn && width >= 900
    readonly property bool stageShown: stageOn && width >= 1180

    readonly property real railW: railShown ? 256 * dp : 0
    readonly property real stageW: stageShown
        ? Math.min(900 * dp, Math.max(420 * dp, width * 0.36))
        : 0

    // ============================================================
    // МОДЕЛЬ СООБЩЕНИЙ
    // ============================================================
    ListModel { id: messages }

    function nowTime() {
        return Qt.formatTime(new Date(), "HH:mm")
    }

    function fmtNum(n) {
        var s = String(n)
        var out = ""
        var c = 0
        for (var i = s.length - 1; i >= 0; --i) {
            out = s.charAt(i) + out
            if (++c % 3 === 0 && i > 0) out = " " + out
        }
        return out
    }

    function appendMessage(role, text) {
        // системный лог режима кода идёт подряд — перезаписываем, а не копим
        if (role === "system" && messages.count > 0) {
            var last = messages.get(messages.count - 1)
            if (last.role === "system") {
                if (last.text === text) return
                var isCode = text.indexOf("режим кода") >= 0
                var wasCode = last.text.indexOf("режим кода") >= 0
                if (isCode && wasCode) {
                    messages.setProperty(messages.count - 1, "text", text)
                    view.ensureAtBottom()
                    return
                }
            }
        }
        messages.append({ role: role, text: text, time: nowTime() })
        if (role === "user") view.scrollToBottomNow()
        else view.ensureAtBottom()
    }

    function send() {
        var t = input.text
        if (t.trim() === "") return
        input.text = ""
        if (t.charAt(0) !== "/") appendMessage("user", t)
        root.isThinking = true
        root.isPrinting = false
        brain.sendMessage(t)
    }

    TextEdit { id: clipHelper; visible: false; width: 4; height: 4 }

    function copyMessage(t) {
        clipHelper.text = t
        clipHelper.selectAll()
        clipHelper.copy()
        root.appendMessage("system", "скопировано в буфер")
    }

    function regenerateStub() {
        root.setDemoState("stream")
    }

    function voiceStub() {
        root.appendMessage("system", "озвучивание — заглушка")
    }

    // ============================================================
    // ДЕМО-СОСТОЯНИЯ (заглушки, потом уберём)
    // ============================================================
    function seedDialog() {
        messages.clear()
        messages.append({ role: "assistant", text: "Привет! Я рядом. Можем вернуться к дизайну чата — или начать с чистого листа, как тебе удобнее.", time: "14:52", think: false })
        messages.append({ role: "user", text: "Помоги переделать экран чата. На широком мониторе справа пусто, а текст теряется на фоне.", time: "14:57", think: false })
        messages.append({ role: "assistant", text: "Тут две разные проблемы, и лечатся они по-разному.\n\n**Пустота справа** — это не про ширину, а про отсутствие второго слоя. У чата есть что показать рядом: присутствие, параметры, голос.\n\n**Текст «теряется»**, потому что панели полупрозрачные и арт просвечивает прямо под буквами.\n\n1. Арт получает свою сцену — он больше не служит фоном для текста.\n2. Диалог садится на плотную поверхность и держит контраст.\n3. Параметры уходят в панель, которая открывается по запросу.\n\nТак экран заполняется смыслом, а не декором. Оставляем?", time: "14:58", think: true })
    }

    function setDemoState(st) {
        root.statusOverride = ""
        root.paramsOpen = false
        root.stageOn = true
        root.isThinking = false
        root.isPrinting = false
        demoTyping.running = false

        if (st === "empty") { messages.clear(); return }

        if (st === "long") {
            messages.clear()
            messages.append({ role: "user", text: "Как устроен запуск модели на 4-битной квантизации?", time: "15:12", think: false })
            messages.append({ role: "assistant", text: "Коротко: веса лежат в 4 битах, а вычисления идут в 16.\n\n**Что происходит по шагам**\n\n1. Веса нарезаются на блоки по 64 значения.\n2. Для каждого блока считается масштаб.\n3. При умножении блок разворачивается в 16 бит на лету.\n\n`python\nfrom transformers import BitsAndBytesConfig\ncfg = BitsAndBytesConfig(load_in_4bit=True)\n`\n\nНа 7B это экономит около 11 ГБ видеопамяти.", time: "15:13", think: false })
            return
        }

        seedDialog()
        if (st === "params") root.paramsOpen = true
        if (st === "nostage") root.stageOn = false
        if (st === "link") root.statusOverride = "ПЕРЕПОДКЛЮЧЕНИЕ… [2]"
        if (st === "stream") {
            root.isThinking = true
            demoTyping.full = "Могу помочь с текстом, кодом и разбором проекта. Работаю локально: ни одно сообщение не уходит в сеть. Скажи, с чего начнём."
            demoTyping.pos = 0
            messages.append({ role: "assistant", text: "", time: "сейчас", think: false })
            demoTyping.running = true
        }
    }

    // ============================================================
    // MARKDOWN -> RICH TEXT
    // ============================================================
    function escHtml(s) {
        return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
                .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    }

    // размеры чата: в демо это фиксированные px на >=2300 и CSS px ниже
    function chatPx(atWide, cssBase) {
        // на >=2300 демо фиксирует физические px, ниже — CSS px с общим zoom
        return width >= 2300 ? atWide : cssBase * dp
    }

    function mdInline(raw) {
        var s = escHtml(raw)
        s = s.replace(/`([^`]+)`/g,
            '<span style="font-family:\'Cascadia Code\'; color:#9CC3F0; background-color:#101725;">$1</span>')
        s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
        s = s.replace(/__([^_]+)__/g, "<b>$1</b>")
        s = s.replace(/(^|[^*])[*]([^*]+)[*]/g, "$1<i>$2</i>")
        s = s.replace(/(^|[^_])[_]([^_]+)[_]/g, "$1<i>$2</i>")
        s = s.replace(/~~([^~]+)~~/g, "<s>$1</s>")
        s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
            '<a href="$2" style="color:#7FB2F0;">$1</a>')
        return s
    }

    function parseBlocks(md) {
        var lines = String(md).split("\n")
        var out = []
        var i = 0
        while (i < lines.length) {
            var line = lines[i]
            if (/^`/.test(line)) {
                var buf = []
                ++i
                while (i < lines.length && !/^`/.test(lines[i])) { buf.push(lines[i]); ++i }
                ++i
                if (buf.length) out.push({ kind: "code", text: buf.join("\n") })
                continue
            }
            var h = line.match(/^(#{1,4})\s+(.*)$/)
            if (h) {
                out.push({ kind: "h", level: h[1].length, text: h[2] })
                ++i
                continue
            }
            if (/^\s*[-*+]\s+/.test(line)) {
                var items = []
                while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                    items.push(lines[i].replace(/^\s*[-*+]\s+/, ""))
                    ++i
                }
                out.push({ kind: "ul", items: items })
                continue
            }
            if (/^\s*\d+\.\s+/.test(line)) {
                var oitems = []
                while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                    oitems.push(lines[i].replace(/^\s*\d+\.\s+/, ""))
                    ++i
                }
                out.push({ kind: "ol", items: oitems })
                continue
            }
            if (!line.trim()) { ++i; continue }
            out.push({ kind: "p", text: line })
            ++i
        }
        return out
    }

    function codeBlockHtml(code) {
        var e = escHtml(code).replace(/\n/g, "<br/>")
        return '<table width="100%" cellspacing="0" cellpadding="0" border="0" '
            + 'style="margin-top:6px; margin-bottom:6px;">'
            + '<tr><td bgcolor="#080d16" style="border:1px solid #1a2433; padding:8px;">'
            + '<pre style="font-family:\'Cascadia Code\'; font-size:12px; color:#B9CBE0;">'
            + e + '</pre></td></tr></table>'
    }

    function mdToHtml(md) {
        var lines = md.split("\n")
        var html = ""
        var i = 0
        var inCode = false
        var codeBuf = []

        while (i < lines.length) {
            var line = lines[i]

            if (/^```/.test(line)) {
                if (!inCode) { inCode = true; codeBuf = [] }
                else { html += codeBlockHtml(codeBuf.join("\n")); inCode = false }
                ++i
                continue
            }
            if (inCode) { codeBuf.push(line); ++i; continue }

            var h = line.match(/^(#{1,4})\s+(.*)$/)
            if (h) {
                var lvl = h[1].length
                var hSize = lvl === 1 ? 18 : lvl === 2 ? 16 : 14
                html += '<p style="font-size:' + Math.round(hSize * root.fp) + 'px; font-weight:600; '
                    + 'margin-top:6px; margin-bottom:4px;">' + mdInline(h[2]) + '</p>'
                ++i
                continue
            }

            if (/^\s*[-*+]\s+/.test(line)) {
                html += '<ul style="margin-top:2px; margin-bottom:2px;">'
                while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                    html += '<li>' + mdInline(lines[i].replace(/^\s*[-*+]\s+/, "")) + '</li>'
                    ++i
                }
                html += '</ul>'
                continue
            }

            if (/^\s*\d+\.\s+/.test(line)) {
                html += '<ol style="margin-top:4px; margin-bottom:2px;">'
                while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                    html += '<li>' + mdInline(lines[i].replace(/^\s*\d+\.\s+/, "")) + '</li>'
                    ++i
                }
                html += '</ol>'
                continue
            }

            if (/^\s*>\s?/.test(line)) {
                html += '<p style="color:#74869E; margin-left:8px;">'
                    + mdInline(line.replace(/^\s*>\s?/, "")) + '</p>'
                ++i
                continue
            }

            if (!line.trim()) { ++i; continue }

            html += '<p style="margin-top:2px; margin-bottom:2px;">' + mdInline(line) + '</p>'
            ++i
        }

        if (inCode) html += codeBlockHtml(codeBuf.join("\n"))
        return html
    }

    // ============================================================
    // СЕССИИ
    // ============================================================
    ListModel { id: sessionsModel }
    property string sessionFilter: ""

    function refreshSessions() {
        sessionsModel.clear()
        var list = brain.sessionList()
        for (var i = 0; i < list.length; ++i) {
            if (root.sessionFilter === "" || list[i].toLowerCase().indexOf(root.sessionFilter.toLowerCase()) >= 0)
                sessionsModel.append({ name: list[i] })
        }
    }

    // ============================================================
    // КОРЕНЬ РАСКЛАДКИ
    // ============================================================
    Rectangle {
        anchors.fill: parent
        color: root.cBg
        z: -1000
    }

    Shortcut {
        sequence: "F11"
        onActivated: {
            if (root.visibility === Window.FullScreen) root.showNormal()
            else root.showFullScreen()
        }
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.visibility === Window.FullScreen
        onActivated: root.showNormal()
    }

    Timer {
        id: demoTyping
        property string full: ""
        property int pos: 0
        interval: 24
        repeat: true
        running: false

        onTriggered: {
            pos += 1
            if (messages.count > 0)
                messages.setProperty(messages.count - 1, "text", full.slice(0, pos))
            if (pos > 1) root.isPrinting = true
            if (pos >= full.length) {
                running = false
                root.isThinking = false
                root.isPrinting = false
            }
        }
    }

    // ============================================================
    // СВОЙ ЗАГОЛОВОК ОКНА
    // ============================================================
    Item {
        id: titleBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 40 * root.dp
        z: 100

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.015, 0.03, 0.055, 0.72)
        }
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: root.cLine
        }

        // перетаскивание окна — под кнопками, чтобы не перехватывать клики
        MouseArea {
            id: dragArea
            anchors.fill: parent
            onPressed: (mouse) => {
                if (mouse.button === Qt.LeftButton) root.startSystemMove()
            }
            onDoubleClicked: {
                if (root.visibility === Window.Maximized) root.showNormal()
                else root.showMaximized()
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Math.round(12 * root.dp)
            anchors.rightMargin: 0
            spacing: 0

            Item {
                Layout.preferredWidth: 26 * root.dp
                Layout.preferredHeight: 26 * root.dp

                IconImage {
                    anchors.centerIn: parent
                    name: "panel-left"
                    iconSize: 14 * root.dp
                    tint: railToggleArea.containsMouse ? root.cText : "#7E8FA6"
                }
                MouseArea {
                    id: railToggleArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.railOn = !root.railOn
                }
            }

            Rectangle {
                Layout.leftMargin: 10 * root.dp
                Layout.preferredWidth: 18 * root.dp
                Layout.preferredHeight: 18 * root.dp
                radius: 5 * root.dp
                clip: true
                color: "#0b1220"
                Image {
                    anchors.fill: parent
                    source: root.avatarSource
                    fillMode: Image.PreserveAspectCrop
                    mipmap: true
                    asynchronous: true
                }
            }

            Text {
                Layout.leftMargin: 10 * root.dp
                text: "НЕЙРА"
                color: "#DBE7F8"
                font.family: root.fMono
                font.pointSize: 10 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
                font.letterSpacing: 3.4 * root.dp
            }
            Text {
                Layout.leftMargin: 8 * root.dp
                text: "/"
                color: root.cText4
                font.family: root.fMono
                font.pointSize: 9 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
            }
            Text {
                text: root.chatTitle.toUpperCase()
                color: root.cText4
                font.family: root.fMono
                font.pointSize: 9 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
                font.letterSpacing: 1.44 * root.dp
            }

            Item { Layout.fillWidth: true }

            // DEMO-чип (как в демо, потом уберём)
            Rectangle {
                id: demoChip
                Layout.preferredWidth: 58 * root.dp
                Layout.preferredHeight: 20 * root.dp
                Layout.rightMargin: 10 * root.dp
                radius: 4 * root.dp
                color: Qt.rgba(0.55, 0.70, 0.90, 0.05)
                border.width: 1
                border.color: Qt.rgba(0.59, 0.72, 0.89, 0.18)

                Row {
                    anchors.centerIn: parent
                    spacing: 5 * root.dp
                    Rectangle {
                        width: 4 * root.dp
                        height: 4 * root.dp
                        radius: 2 * root.dp
                        color: root.cOk
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "DEMO"
                        color: "#8FA6C4"
                        font.family: root.fMono
                        font.pointSize: 7.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        font.letterSpacing: 1.4
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: demoMenu.opened ? demoMenu.close() : demoMenu.open()
                }
            }

            // сворачивание
            Item {
                Layout.preferredWidth: 44 * root.dp
                Layout.preferredHeight: titleBar.height
                IconImage {
                    anchors.centerIn: parent
                    name: "minus"
                    iconSize: 13 * root.dp
                    tint: minArea.containsMouse ? root.cText : root.cText3
                }
                MouseArea {
                    id: minArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.showMinimized()
                }
                Rectangle {
                    anchors.fill: parent
                    color: minArea.containsMouse ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
                    z: -1
                }
            }

            // развернуть
            Item {
                Layout.preferredWidth: 44 * root.dp
                Layout.preferredHeight: titleBar.height
                IconImage {
                    anchors.centerIn: parent
                    name: "square"
                    iconSize: 12 * root.dp
                    tint: maxArea.containsMouse ? root.cText : root.cText3
                }
                MouseArea {
                    id: maxArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (root.visibility === Window.Maximized) root.showNormal()
                        else root.showMaximized()
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    color: maxArea.containsMouse ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
                    z: -1
                }
            }

            // закрыть
            Item {
                Layout.preferredWidth: 44 * root.dp
                Layout.preferredHeight: titleBar.height
                Rectangle {
                    anchors.fill: parent
                    color: winCloseArea.containsMouse ? Qt.rgba(1, 0.42, 0, 0.10) : "transparent"
                }
                IconImage {
                    anchors.centerIn: parent
                    name: "x"
                    iconSize: 13 * root.dp
                    tint: winCloseArea.containsMouse ? "#FF6C00" : root.cText3
                }
                MouseArea {
                    id: winCloseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.close()
                }
            }
        }
    }

    RowLayout {
        id: contentRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: titleBar.bottom
        anchors.bottom: parent.bottom
        spacing: 0

        // ========================================================
        // ЛЕВАЯ ПАНЕЛЬ
        // ========================================================
        Item {
            id: rail
            implicitWidth: root.railW
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            clip: true
            Behavior on implicitWidth { NumberAnimation { duration: 320; easing.type: Easing.InOutCubic } }

            Rectangle { anchors.fill: parent; color: root.cRail; opacity: 0.86 }
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: root.cLine }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 12 * root.dp
                anchors.rightMargin: Math.round(12 * root.dp)
                anchors.topMargin: Math.round(14 * root.dp) - 1
                anchors.bottomMargin: 10 * root.dp
                spacing: 10 * root.dp

                // новый разговор
                Rectangle {
                    id: newChatBtn
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38 * root.dp
                    radius: 9 * root.dp
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: newChatArea.containsMouse ? "#F4F8FF" : "#EAF2FF" }
                        GradientStop { position: 1.0; color: newChatArea.containsMouse ? "#D3E4FB" : "#C3D9F8" }
                    }


                    // внешняя тень как box-shadow: 0 10px 24px -12px rgba(120,170,230,.55)
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: 1
                        color: Qt.rgba(1, 1, 1, 0.7)
                    }

                    Rectangle {
                        anchors.top: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width - 24 * root.dp
                        height: 24 * root.dp
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.rgba(120 / 255, 170 / 255, 230 / 255, 0.10) }
                            GradientStop { position: 1.0; color: "transparent" }
                        }
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 14 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8 * root.dp
                        IconImage {
                            anchors.verticalCenter: parent.verticalCenter
                            name: "plus"
                            iconSize: 12 * root.dp
                            tint: "#0b1a30"
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "НОВЫЙ РАЗГОВОР"
                            color: "#050e1c"
                            font.family: root.fMono
                            font.pointSize: 9.5 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 1.6
                        }
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 14 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        text: "^N"
                        color: "#7d90aa"
                        font.family: root.fMono
                        font.pointSize: 8.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    MouseArea {
                        id: newChatArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.isThinking || root.isPrinting) {
                                appendMessage("system", "подожди — ответ ещё идёт")
                                return
                            }
                            messages.clear()
                            brain.clearHistory()
                            appendMessage("system", "Нейра здесь. О чём поговорим?")
                            input.forceActiveFocus()
                        }
                    }
                }

                // поиск
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32 * root.dp
                    radius: 9 * root.dp
                    color: Qt.rgba(140 / 255, 180 / 255, 230 / 255, 0.035)
                    border.width: 1
                    border.color: searchField.activeFocus ? root.cLine2 : root.cLine

                    TextInput {
                        id: searchField
                        anchors.fill: parent
                        anchors.leftMargin: 30 * root.dp
                        anchors.rightMargin: 10 * root.dp
                        verticalAlignment: TextInput.AlignVCenter
                        color: root.cText2
                        font.family: root.fSans
                        font.pointSize: 12 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        selectByMouse: true
                        onTextChanged: {
                            root.sessionFilter = text
                            root.refreshSessions()
                        }
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 30 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        visible: searchField.text === ""
                        text: "Поиск по чатам"
                        color: root.cText4
                        font.family: root.fSans
                        font.pointSize: 12 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    IconImage {
                        x: 10 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        name: "search"
                        iconSize: 12 * root.dp
                        tint: root.cText4
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 10 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        text: "^K"
                        color: "#5b6b82"
                        font.family: root.fMono
                        font.pointSize: 8.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                }

                // 01 СЕГОДНЯ
                RailSection { Layout.fillWidth: true; num: "01"; title: "СЕГОДНЯ" }
                RailChat { Layout.fillWidth: true; title: "Дизайн чата"; sub: "Переделать экран под широкий монитор"; time: "14:58"; active: root.activeChat === 0; onClicked: { root.activeChat = 0; root.chatTitle = "Дизайн чата" } }
                RailChat { Layout.fillWidth: true; title: "Идеи для Нейры"; sub: "Характер, голос, реакции"; time: "13:20"; active: root.activeChat === 1; onClicked: { root.activeChat = 1; root.chatTitle = "Идеи для Нейры" } }
                RailChat { Layout.fillWidth: true; title: "Стихи про звёзды"; sub: "Три варианта, ночь, тишина"; time: "11:04"; active: root.activeChat === 2; onClicked: { root.activeChat = 2; root.chatTitle = "Стихи про звёзды" } }

                // 02 ВЧЕРА
                RailSection { Layout.fillWidth: true; num: "02"; title: "ВЧЕРА"; Layout.topMargin: 2.8 * root.dp }
                RailChat { Layout.fillWidth: true; title: "Настройка голоса"; sub: "Темп, тембр, паузы"; time: "21:40"; active: root.activeChat === 3; onClicked: { root.activeChat = 3; root.chatTitle = "Настройка голоса" } }
                RailChat { Layout.fillWidth: true; title: "Промпт-инженер"; sub: "Системные инструкции"; time: "19:12"; active: root.activeChat === 4; onClicked: { root.activeChat = 4; root.chatTitle = "Промпт-инженер" } }

                // 03 РАНЕЕ
                RailSection { Layout.fillWidth: true; num: "03"; title: "РАНЕЕ"; Layout.topMargin: 2.8 * root.dp; Layout.bottomMargin: 3 * root.dp }
                RailChat { Layout.fillWidth: true; title: "Заметки о модели"; sub: "Квантизация, скорость"; time: "28.10"; active: root.activeChat === 5; onClicked: { root.activeChat = 5; root.chatTitle = "Заметки о модели" } }

                Item { Layout.fillHeight: true }

                // низ панели
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: root.cLine
                }

                // голос
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32 * root.dp
                    radius: 7 * root.dp
                    color: voiceRowArea.containsMouse ? Qt.rgba(0.55, 0.70, 0.90, 0.06) : "transparent"

                    IconImage {
                        x: 9 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        name: "wave"
                        iconSize: 13 * root.dp
                        tint: root.cText3
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 28 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Голос"
                        color: root.cText2
                        font.family: root.fSans
                        font.pointSize: 11.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    Rectangle {
                        anchors.right: parent.right
                        anchors.rightMargin: 9 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        width: 24 * root.dp
                        height: 15 * root.dp
                        radius: 3 * root.dp
                        color: Qt.rgba(0.44, 0.89, 0.76, 0.08)
                        border.width: 1
                        border.color: Qt.rgba(0.44, 0.89, 0.76, 0.24)
                        Text {
                            anchors.centerIn: parent
                            text: "ON"
                            color: root.cOk
                            font.family: root.fMono
                            font.pointSize: 8 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 0.8
                        }
                    }
                    MouseArea {
                        id: voiceRowArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                    }
                }

                // сохранить
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32 * root.dp
                    radius: 7 * root.dp
                    color: paramsArea.containsMouse ? Qt.rgba(0.55, 0.70, 0.90, 0.06) : "transparent"

                    IconImage {
                        x: 9 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        name: "sliders"
                        iconSize: 13 * root.dp
                        tint: root.cText3
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 28 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Параметры"
                        color: root.cText2
                        font.family: root.fSans
                        font.pointSize: 11.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    MouseArea {
                        id: paramsArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.paramsOpen = !root.paramsOpen
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 4 * root.dp
                    spacing: 9 * root.dp

                    Rectangle {
                        Layout.preferredWidth: 26 * root.dp
                        Layout.preferredHeight: 26 * root.dp
                        radius: 8 * root.dp
                        clip: true
                        color: "#0b1220"
                        Image {
                            anchors.fill: parent
                            source: root.avatarSource
                            fillMode: Image.PreserveAspectCrop
                            mipmap: true
                            asynchronous: true
                        }
                    }
                    Column {
                        spacing: 1
                        Text {
                            text: "Никита"
                            color: "#DCE0EC"
                            font.family: root.fSans
                            font.pointSize: 11.5 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: "Local session"
                            color: root.cText4
                            font.family: root.fMono
                            font.pointSize: 8 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 1
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Item {
                        Layout.preferredWidth: 16 * root.dp
                        Layout.preferredHeight: 16 * root.dp
                        IconImage {
                            anchors.centerIn: parent
                            name: "gear"
                            iconSize: 13 * root.dp
                            tint: root.cText4
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
            }
        }

        // ========================================================
        // ЦЕНТР
        // ========================================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.rightMargin: root.mainRightPad

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // ---------- шапка ----------
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56 * root.dp

                    Rectangle { anchors.fill: parent; color: Qt.rgba(0.02, 0.03, 0.05, 0.42) }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.cLine }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Math.max(22 * root.dp, (parent.width - 720 * root.fp) / 2)
                        anchors.rightMargin: Math.max(18 * root.dp, (parent.width - 720 * root.fp) / 2)
                        spacing: 3 * root.dp

                        // аватар
                        Item {
                            Layout.preferredWidth: 30 * root.dp
                            Layout.preferredHeight: 30 * root.dp

                            Rectangle {
                                anchors.fill: parent
                                radius: 8 * root.dp
                                clip: true
                                color: "#0b1220"
                                Image {
                                    anchors.fill: parent
                                    source: root.avatarSource
                                    fillMode: Image.PreserveAspectCrop
                                    mipmap: true
                                    asynchronous: true
                                }
                            }
                            Rectangle {
                                anchors.fill: parent
                                radius: 8 * root.dp
                                color: "transparent"
                                border.width: 1
                                border.color: Qt.rgba(0.75, 0.85, 0.94, 0.26)
                            }
                            // точка статуса
                            Rectangle {
                                width: 8 * root.dp; height: 8 * root.dp; radius: width / 2
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.rightMargin: -1
                                anchors.bottomMargin: -1
                                border.width: 2 * root.dp
                                border.color: "#060b14"
                                color: root.isThinking || root.isPrinting ? "#00C8E0"
                                     : brain.connectionStatus === "connected" ? root.cOk
                                     : brain.connectionStatus === "failed" ? root.cBad
                                     : root.cWarn
                            }
                        }

                        ColumnLayout {
                            spacing: 1
                            Text {
                                text: "Нейра"
                                color: "#EDF3FC"
                                font.family: root.fSans
                                font.pointSize: 13 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                spacing: 6 * root.dp

                                Text {
                                    text: root.statusOverride !== "" ? root.statusOverride
                                        : root.isThinking || root.isPrinting ? "ПЕЧАТАЕТ…"
                                        : brain.connectionStatus === "connected" ? "ONLINE"
                                        : brain.connectionStatus === "failed" ? "СВЯЗЬ ПОТЕРЯНА"
                                        : "ПЕРЕПОДКЛЮЧЕНИЕ…" + (brain.reconnectAttempt > 0 ? " [" + brain.reconnectAttempt + "]" : "")
                                    color: root.statusOverride !== "" ? root.cWarn
                                         : root.isThinking || root.isPrinting ? "#7FE3F0"
                                         : brain.connectionStatus === "connected" ? "#8FA6C4"
                                         : brain.connectionStatus === "failed" ? root.cBad
                                         : root.cWarn
                                    font.family: root.fMono
                                    font.pointSize: 8.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 1.45

                                    SequentialAnimation on opacity {
                                        running: root.isThinking || root.isPrinting
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1.0; to: 0.42; duration: 700; easing.type: Easing.InOutQuad }
                                        NumberAnimation { from: 0.42; to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
                                    }
                                }

                                Text {
                                    visible: brain.connectionStatus === "connected" && root.statusOverride === ""
                                    text: "· MISTRAL 7B · ЛОКАЛЬНО"
                                    color: root.cText4
                                    font.family: root.fMono
                                    font.pointSize: 8.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 1.45
                                }
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // режим кода
                        Rectangle {
                            visible: brain.codeMode
                            Layout.preferredHeight: 22 * root.dp
                            Layout.preferredWidth: codeLabel.implicitWidth + 18 * root.dp
                            radius: 4 * root.dp
                            color: Qt.rgba(0.66, 0.78, 0.94, 0.08)
                            border.width: root.pen
                            border.color: Qt.rgba(0.66, 0.78, 0.94, 0.28)

                            Text {
                                id: codeLabel
                                anchors.centerIn: parent
                                text: "</> КОД"
                                color: root.cIce2
                                font.family: root.fMono
                                font.pointSize: 8 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                        }

                        // голос
                        Item {
                            Layout.preferredWidth: 27 * root.dp
                            Layout.preferredHeight: 27 * root.dp

                            Rectangle {
                                anchors.fill: parent
                                radius: 6 * root.dp
                                color: voiceToggle.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.08) : "transparent"
                                border.width: 1
                                border.color: voiceToggle.containsMouse ? root.cLine2 : root.cLine
                            }
                            IconImage {
                                anchors.centerIn: parent
                                name: "volume"
                                iconSize: 15 * root.dp
                                tint: voiceToggle.containsMouse ? root.cIce : root.cText2
                            }
                            MouseArea {
                                id: voiceToggle
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                            }
                        }

                        // сцена
                        Item {
                            Layout.preferredWidth: 27 * root.dp
                            Layout.preferredHeight: 27 * root.dp

                            Rectangle {
                                anchors.fill: parent
                                radius: 6 * root.dp
                                color: stageToggle.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.08) : "transparent"
                                border.width: 1
                                border.color: root.stageOn ? Qt.rgba(0.55, 0.70, 0.90, 0.22) : (stageToggle.containsMouse ? root.cLine2 : root.cLine)
                            }
                            IconImage {
                                anchors.centerIn: parent
                                name: "panel"
                                iconSize: 15 * root.dp
                                tint: stageToggle.containsMouse ? root.cIce : root.cText2
                            }
                            MouseArea {
                                id: stageToggle
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.stageOn = !root.stageOn
                            }
                        }

                        // параметры
                        Item {
                            Layout.preferredWidth: 27 * root.dp
                            Layout.preferredHeight: 27 * root.dp
                            Layout.leftMargin: 4 * root.dp

                            Rectangle {
                                anchors.fill: parent
                                radius: 6 * root.dp
                                color: paramsToggle.containsMouse || root.paramsOpen ? Qt.rgba(0.62, 0.76, 0.92, 0.10) : "transparent"
                            }
                            IconImage {
                                anchors.centerIn: parent
                                name: "sliders"
                                iconSize: 15 * root.dp
                                tint: paramsToggle.containsMouse ? root.cIce : root.cText2
                            }
                            MouseArea {
                                id: paramsToggle
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.paramsOpen = !root.paramsOpen
                            }
                        }

                        // разделитель
                        Rectangle {
                            Layout.preferredWidth: 1
                            Layout.preferredHeight: 15 * root.dp
                            Layout.leftMargin: 2 * root.dp
                            color: root.cLine2
                        }

                        // ещё
                        Item {
                            Layout.preferredWidth: 27 * root.dp
                            Layout.preferredHeight: 27 * root.dp
                            Layout.leftMargin: 2 * root.dp

                            Rectangle {
                                anchors.fill: parent
                                radius: 6 * root.dp
                                color: moreArea.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.10) : "transparent"
                            }
                            IconImage {
                                anchors.centerIn: parent
                                name: "more"
                                iconSize: 15 * root.dp
                                tint: moreArea.containsMouse ? root.cIce : root.cText2
                            }
                            MouseArea {
                                id: moreArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                            }
                        }
                    }
                }

                // ---------- лента ----------
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: view
                        anchors.fill: parent
                        anchors.topMargin: 4 * root.dp
                        anchors.bottomMargin: 8 * root.dp
                        anchors.leftMargin: Math.max(20 * root.dp, (parent.width - 720 * root.fp) / 2)
                        anchors.rightMargin: Math.max(20 * root.dp, (parent.width - 720 * root.fp) / 2)
                        clip: true
                        spacing: 1 * root.dp
                        model: messages

                        // Без add: Transition — пока она идёт, ListView не двигает
                        // соседей при смене высоты делегата (текст переносится уже
                        // после создания) и в ленте остаётся дыра. Плавное появление —
                        // внутри делегата (fadeIn), геометрию оно не трогает.

                        header: Item {
                            width: view.width
                            height: 46 * root.dp

                            Item {
                                id: dayRow
                                width: parent.width
                                height: 28 * root.dp
                                anchors.top: parent.top

                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width
                                    height: 1
                                    color: root.cLine
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: dayText.implicitWidth + 20 * root.dp
                                    height: parent.height
                                    color: root.cBg
                                }
                                Text {
                                    id: dayText
                                    anchors.centerIn: parent
                                    text: Qt.formatDate(new Date(), "dd.MM") + " / СЕГОДНЯ"
                                    color: root.cText4
                                    font.family: root.fMono
                                    font.pointSize: 8 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 1.4
                                }
                            }
                        }
                        boundsBehavior: Flickable.StopAtBounds
                        cacheBuffer: 600

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
                            contentItem: Rectangle {
                                implicitWidth: 4
                                implicitHeight: 40
                                radius: 2
                                color: Qt.rgba(0.59, 0.72, 0.89, 0.16)
                            }
                        }

                        delegate: Item {
                            id: del
                            width: view.width
                            height: bodyColumn.implicitHeight + 18 * root.dp

                            NumberAnimation { id: fadeIn; target: del; property: "opacity"; from: 0; to: 1; duration: 220 }
                            Component.onCompleted: if (index === view.count - 1) fadeIn.start()

                            Column {
                                id: bodyColumn
                                y: 9 * root.dp
                                width: parent.width
                                spacing: 0

                                // ---- системный лог ----
                                Item {
                                    visible: model.role === "system"
                                    width: parent.width
                                    height: sysPill.height + 6 * root.dp

                                    Text {
                                        id: sysMeasure
                                        visible: false
                                        text: model.text
                                        font.family: root.fMono
                                        font.pointSize: 9 * root.fp * 0.75
                                        font.hintingPreference: Font.PreferNoHinting
                                    }
                                    Rectangle {
                                        id: sysPill
                                        anchors.centerIn: parent
                                        width: Math.min(sysMeasure.implicitWidth + 30 * root.dp, parent.width - 40 * root.dp)
                                        height: sysText.implicitHeight + 10 * root.dp
                                        radius: height / 2
                                        color: Qt.rgba(1.0, 0.42, 0.0, 0.055)
                                        border.width: root.pen
                                        border.color: Qt.rgba(1.0, 0.42, 0.0, 0.26)

                                        Text {
                                            id: sysText
                                            anchors.centerIn: parent
                                            width: parent.width - 24 * root.dp
                                            text: "<b>[SYS]</b> " + model.text
                                            textFormat: Text.RichText
                                            wrapMode: Text.Wrap
                                            horizontalAlignment: Text.AlignHCenter
                                            color: "#B99A80"
                                            font.family: root.fMono
                                            font.pointSize: 9 * root.fp * 0.75
                                            font.hintingPreference: Font.PreferNoHinting
                                            font.letterSpacing: 0.6
                                        }
                                    }
                                }

                                // ---- Нейра ----
                                Item {
                                    visible: model.role === "assistant"
                                    width: parent.width
                                    height: aRow.height + 8 * root.dp

                                    Row {
                                        id: aRow
                                        width: parent.width
                                        spacing: 10 * root.dp

                                        Item {
                                            width: 24 * root.dp
                                            height: 24 * root.dp
                                            Rectangle {
                                                anchors.fill: parent
                                                radius: 7 * root.dp
                                                clip: true
                                                color: "#0b1220"
                                                Image {
                                                    anchors.fill: parent
                                                    source: root.avatarSource
                                                    fillMode: Image.PreserveAspectCrop
                                                    mipmap: true
                                                    asynchronous: true
                                                }
                                            }
                                        }

                                        Column {
                                            width: Math.min(parent.width - 34 * root.dp, 713)
                                            spacing: 4 * root.dp

                                            RowLayout {
                                                spacing: 8 * root.dp
                                                Text {
                                                    text: "Нейра"
                                                    color: "#DCE6F3"
                                                    font.family: root.fSans
                                                    font.pointSize: 12 * root.fp * 0.75
                                                    font.hintingPreference: Font.PreferNoHinting
                                                    font.weight: Font.DemiBold
                                                }
                                                Rectangle {
                                                    Layout.alignment: Qt.AlignVCenter
                                                    Layout.preferredWidth: 20 * root.dp
                                                    Layout.preferredHeight: 13 * root.dp
                                                    radius: 3 * root.dp
                                                    color: "transparent"
                                                    border.width: 1
                                                    border.color: Qt.rgba(0.59, 0.72, 0.89, 0.25)
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: "AI"
                                                        color: "#8FA6C4"
                                                        font.family: root.fMono
                                                        font.pointSize: root.chatPx(9.8, 7.5) * 0.75
                                                        font.hintingPreference: Font.PreferNoHinting
                                                        font.letterSpacing: 0.5
                                                    }
                                                }
                                                Text {
                                                    Layout.alignment: Qt.AlignBaseline
                                                    text: model.time
                                                    color: root.cText4
                                                    font.family: root.fMono
                                font.pointSize: root.chatPx(9.8, 8.5) * 0.75
                                                    font.hintingPreference: Font.PreferNoHinting
                                                }
                                            }

                                            Rectangle {
                                                visible: model.think === true
                                                width: thinkRow.implicitWidth + 16 * root.dp
                                                height: 23 * root.dp
                                                radius: 4 * root.dp
                                                color: Qt.rgba(0.55, 0.71, 0.90, 0.04)
                                                border.width: 1
                                                border.color: root.cLine

                                                Row {
                                                    id: thinkRow
                                                    anchors.centerIn: parent
                                                    spacing: 6 * root.dp

                                                    IconImage {
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        name: "spark"
                                                        iconSize: 11 * root.dp
                                                        tint: root.cIce2
                                                    }
                                                    Text {
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        text: "РАЗМЫШЛЕНИЕ"
                                                        color: "#7086A0"
                                                        font.family: root.fMono
                                                        font.pointSize: root.chatPx(10, 8) * 0.75
                                                        font.hintingPreference: Font.PreferNoHinting
                                                        font.letterSpacing: 1.04
                                                    }
                                                    Text {
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        text: "2.4S"
                                                        color: "#A8BEDC"
                                                        font.family: root.fMono
                                                        font.pointSize: root.chatPx(10, 8) * 0.75
                                                        font.hintingPreference: Font.PreferNoHinting
                                                        font.letterSpacing: 1.04
                                                    }
                                                }
                                            }

                                            MessageBody {
                                                width: parent.width
                                                source: model.text
                                            }

                                            RowLayout {
                                                visible: index === messages.count - 1
                                                spacing: 1 * root.dp

                                                MsgAction { kind: "copy"; onClicked: root.copyMessage(model.text) }
                                                MsgAction { kind: "refresh"; onClicked: root.regenerateStub() }
                                                MsgAction { kind: "voice"; onClicked: root.voiceStub() }
                                                Rectangle {
                                                    Layout.preferredWidth: 1
                                                    Layout.preferredHeight: 11 * root.dp
                                                    color: root.cLine
                                                    Layout.leftMargin: 4 * root.dp
                                                    Layout.rightMargin: 4 * root.dp
                                                }
                                                MsgAction { kind: "more" }
                                                Text {
                                                    Layout.alignment: Qt.AlignVCenter
                                                    Layout.leftMargin: 6 * root.dp
                                                    text: model.time
                                                    color: root.cText4
                                                    font.family: root.fMono
                                                    font.pointSize: root.chatPx(9.8, 7.5) * 0.75
                                                    font.hintingPreference: Font.PreferNoHinting
                                                }
                                            }
                                        }
                                    }
                                }

                                // ---- пользователь ----
                                Item {
                                    visible: model.role === "user"
                                    width: parent.width
                                    height: uBubble.height + uTime.height + uTime.anchors.topMargin

                                    Text {
                                        id: uMeasure
                                        visible: false
                                        text: model.text
                                        font.family: root.fSans
                                        font.pointSize: 14 * root.fp * 0.75
                                        font.hintingPreference: Font.PreferNoHinting
                                    }
                                    Rectangle {
                                        id: uBubble
                                        anchors.right: parent.right
                                        width: Math.min(uMeasure.implicitWidth + 28 * root.dp, Math.min(parent.width - 40 * root.dp, root.width >= 2300 ? 552 : 520))
                                        height: uText.implicitHeight + 20 * root.dp
                                        radius: 12 * root.dp
                                        gradient: Gradient {
                                            GradientStop { position: 0.0; color: Qt.rgba(0.47, 0.65, 0.86, 0.14) }
                                            GradientStop { position: 1.0; color: Qt.rgba(0.47, 0.65, 0.86, 0.07) }
                                        }
                                        border.width: root.pen
                                        border.color: Qt.rgba(0.59, 0.75, 0.92, 0.20)

                                        MessageBody {
                                            id: uText
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            anchors.leftMargin: 14 * root.dp
                                            anchors.rightMargin: 14 * root.dp
                                            anchors.topMargin: 10 * root.dp
                                            source: model.text
                                            bodyColor: "#E6EEFA"
                                        }
                                    }
                                    Text {
                                        id: uTime
                                        anchors.right: parent.right
                                        anchors.top: uBubble.bottom
                                        anchors.topMargin: 5 * root.dp
                                        text: model.time
                                        color: "#46566B"
                                        font.family: root.fMono
                                        font.pointSize: 8.5 * root.dp * 0.75
                                        font.hintingPreference: Font.PreferNoHinting
                                        font.letterSpacing: 0.5 * root.dp
                                    }
                                }
                            }
                        }
                    }

                    // кнопка «в конец»
                    Item {
                        id: scrollDownBtn
                        width: 30 * root.dp
                        height: 30 * root.dp
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 6 * root.dp
                        visible: view.isScrollingUp && view.contentHeight > view.height + 8

                        Rectangle {
                            anchors.fill: parent
                            radius: 8 * root.dp
                            color: "#0b1220"
                            border.width: root.pen
                            border.color: downArea.containsMouse ? root.cIce2 : root.cLine2
                        }
                        Shape {
                            anchors.centerIn: parent
                            width: 12 * root.dp
                            height: 12 * root.dp
                            ShapePath {
                                strokeColor: downArea.containsMouse ? root.cIce : root.cText3
                                strokeWidth: 1.5 * root.dp
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

                // ---------- композер ----------
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: composerColumn.implicitHeight
                    Layout.bottomMargin: 12 * root.dp

                    Column {
                        id: composerColumn
                        width: parent.width
                        spacing: 6 * root.dp

                        Rectangle {
                            id: shell
                            x: Math.max(22 * root.dp, (parent.width - 720 * root.fp) / 2)
                            width: Math.min(parent.width - 44 * root.dp, 720 * root.fp)
                            height: 86 * root.dp
                            radius: 14 * root.dp
                            color: "#080d16"
                            border.width: 1
                            border.color: input.activeFocus ? Qt.rgba(0.78, 0.86, 0.98, 0.34) : root.cLine2

                            ScrollView {
                                id: inputScroll
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.leftMargin: 14 * root.dp
                                anchors.rightMargin: 14 * root.dp
                                anchors.topMargin: 12 * root.dp
                                height: 40 * root.dp
                                clip: true

                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                TextArea {
                                    id: input
                                    width: inputScroll.availableWidth
                                    color: root.cText
                                    font.family: root.fSans
                                    font.pointSize: 13.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    placeholderText: "Написать Нейре…"
                                    placeholderTextColor: root.cText4
                                    wrapMode: TextEdit.Wrap
                                    selectByMouse: true
                                    topPadding: 0
                                    bottomPadding: 0
                                    background: Rectangle { color: "transparent" }

                                    Keys.onReturnPressed: (event) => {
                                        if (event.modifiers & Qt.ShiftModifier) {
                                            event.accepted = false
                                            return
                                        }
                                        event.accepted = true
                                        root.send()
                                    }
                                    Keys.onEscapePressed: (event) => {
                                        input.text = ""
                                    }
                                }
                            }

                            RowLayout {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: 8 * root.dp
                                anchors.rightMargin: 8 * root.dp
                                anchors.bottomMargin: 7 * root.dp
                                spacing: 2 * root.dp

                                // прикрепить
                                Item {
                                    Layout.preferredWidth: 28 * root.dp
                                    Layout.preferredHeight: 28 * root.dp
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 6 * root.dp
                                        color: attachArea.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.10) : "transparent"
                                    }
                                    IconImage {
                                        anchors.centerIn: parent
                                        name: "paperclip"
                                        iconSize: 15 * root.dp
                                        tint: attachArea.containsMouse ? root.cIce : root.cText3
                                    }
                                    MouseArea {
                                        id: attachArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                    }
                                }

                                // голосовой ввод
                                Item {
                                    Layout.preferredWidth: 28 * root.dp
                                    Layout.preferredHeight: 28 * root.dp
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 6 * root.dp
                                        color: micArea.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.10) : "transparent"
                                    }
                                    IconImage {
                                        anchors.centerIn: parent
                                        name: "mic"
                                        iconSize: 15 * root.dp
                                        tint: micArea.containsMouse ? root.cIce : root.cText3
                                    }
                                    MouseArea {
                                        id: micArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    text: root.fmtNum(brain.totalTokensSpent) + " / " + root.fmtNum(brain.maxTokens > 0 ? brain.maxTokens : 8192)
                                    color: "#7C8CA3"
                                    font.family: root.fMono
                                    font.pointSize: 9.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 0.5
                                }

                                SendButton {
                                    id: sendBtn
                                    size: 30 * root.dp
                                    generating: brain.isGenerating
                                    onClicked: {
                                        if (brain.isGenerating) {
                                            brain.stop()
                                            root.isThinking = false
                                            root.isPrinting = false
                                        } else {
                                            root.send()
                                        }
                                    }
                                }
                            }
                        }

                        RowLayout {
                            x: shell.x + 4 * root.dp
                            width: shell.width - 8 * root.dp
                            spacing: 12 * root.dp

                            Text {
                                text: "ENTER"
                                color: "#93A6BD"
                                font.family: root.fMono
                                font.pointSize: 9.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                            Text {
                                text: "ОТПРАВИТЬ"
                                color: "#7C8CA3"
                                font.family: root.fMono
                                font.pointSize: 9.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                            Text {
                                text: "SHIFT+ENTER"
                                color: "#93A6BD"
                                font.family: root.fMono
                                font.pointSize: 9.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                            Text {
                                text: "НОВАЯ СТРОКА"
                                color: "#7C8CA3"
                                font.family: root.fMono
                                font.pointSize: 9.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredWidth: 3 * root.dp
                                Layout.preferredHeight: 3 * root.dp
                                radius: 1.5 * root.dp
                                color: root.cOk
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    shadowEnabled: true
                                    shadowColor: root.cOk
                                    shadowBlur: 0.8
                                    shadowVerticalOffset: 0
                                    shadowHorizontalOffset: 0
                                    opacity: 0.9
                                }
                            }
                            Text {
                                text: "31,2 T/S · 51 TOK"
                                color: "#7C8CA3"
                                font.family: root.fMono
                                font.pointSize: 9.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1
                            }
                        }

                        Item { width: parent.width; height: 6 * root.dp }
                    }
                }
            }
        }

        // ========================================================
        // СЦЕНА
        // ========================================================
        Item {
            id: stage
            implicitWidth: root.stageW
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            clip: true
            Behavior on implicitWidth { NumberAnimation { duration: 320; easing.type: Easing.InOutCubic } }

            // граница сцены как .stage{border-left:1px solid rgba(150,190,235,.10)}
            Rectangle {
                anchors.left: parent.left
                width: root.pen
                height: parent.height
                z: 3
                color: Qt.rgba(150 / 255, 190 / 255, 235 / 255, 0.10)
            }

            Item {
                anchors.fill: parent
                clip: true

                Image {
                    id: art
                    source: root.artSource
                    asynchronous: true
                    readonly property real sc: Math.max(stage.width / 2607, stage.height / 1608)
                    width: 2607 * sc
                    height: 1608 * sc
                    x: (stage.width - width) * 0.94
                    y: (stage.height - height) * 0.5
                }

                // левая вуаль
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.00; color: "#e604070e" }
                        GradientStop { position: 0.06; color: "#8c04070e" }
                        GradientStop { position: 0.18; color: "#0004070e" }
                    }
                }
                // низ
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.00; color: "#8c04070e" }
                        GradientStop { position: 0.16; color: "#0004070e" }
                        GradientStop { position: 0.58; color: "#0004070e" }
                        GradientStop { position: 0.90; color: "#b804070e" }
                        GradientStop { position: 1.00; color: "#eb04070e" }
                    }
                }
                // правое затемнение
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.55; color: "#0004070e" }
                        GradientStop { position: 1.00; color: "#5904070e" }
                    }
                }
            }

            // голосовая панель (декоративная — до подключения TTS)
            Rectangle {
                id: voiceBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 14 * root.dp
                height: 58 * root.dp
                radius: 12 * root.dp
                color: Qt.rgba(0.02, 0.04, 0.07, 0.74)
                border.width: 1
                border.color: Qt.rgba(0.59, 0.72, 0.89, 0.16)
                visible: stage.width > 220 * root.dp

                // play
                Item {
                    id: playBtn
                    width: 32 * root.dp
                    height: 32 * root.dp
                    anchors.left: parent.left
                    anchors.leftMargin: 10 * root.dp
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        anchors.fill: parent
                        radius: width / 2
                        color: Qt.rgba(0.55, 0.70, 0.90, 0.10)
                        border.width: 1
                        border.color: Qt.rgba(0.75, 0.85, 0.98, 0.45)
                    }
                    IconImage {
                        anchors.centerIn: parent
                        name: "play"
                        iconSize: 11 * root.dp
                        tint: "#EAF2FF"
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor }
                }

                // волна
                Row {
                    anchors.left: playBtn.right
                    anchors.leftMargin: 12 * root.dp
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2 * root.dp

                    Repeater {
                        model: 34
                        Item {
                            width: 2 * root.dp
                            height: 26 * root.dp

                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                height: Math.max(3, 4 + Math.abs(Math.sin(index * 0.55)) * 17
                                                     + (index % 7 === 0 ? 4 : 0)) * root.dp
                                radius: width / 2
                                color: index < 14 ? "#AAC7EF" : Qt.rgba(0.59, 0.72, 0.89, 0.22)
                            }
                        }
                    }
                }

                // статус
            }

            Text {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.leftMargin: 20 * root.dp
                anchors.bottomMargin: 88 * root.dp
                text: "НЕЙРА"
                color: "#B8CCE8"
                font.family: root.fMono
                font.pointSize: 10 * root.fp * 0.75
                font.hintingPreference: Font.PreferNoHinting
                font.letterSpacing: 3.2
                visible: stage.width > 120 * root.dp
            }
        }
    }

    // ============================================================
    // РУЧКА ВОЗВРАТА СЦЕНЫ
    // ============================================================
    Rectangle {
        id: stageHandle
        visible: !root.stageShown && !root.paramsOpen && root.width >= 1180
        anchors.right: parent.right
        anchors.rightMargin: 10 * root.dp
        anchors.verticalCenter: parent.verticalCenter
        width: 24 * root.dp
        height: 54 * root.dp
        radius: 6 * root.dp
        color: "#0b1220"
        border.width: 1
        border.color: handleArea.containsMouse ? root.cIce2 : root.cLine2
        z: 60

        IconImage {
            anchors.centerIn: parent
            name: "chevron-left"
            iconSize: 13 * root.dp
            tint: handleArea.containsMouse ? root.cIce : root.cText3
        }
        MouseArea {
            id: handleArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.stageOn = true
        }
    }

    // ============================================================
    // РЕСАЙЗ БЕЗ РАМКИ (края и нижние углы)
    // ============================================================
    Item {
        anchors.fill: parent
        z: 200
        enabled: root.visibility !== Window.Maximized

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 6 * root.dp
            cursorShape: Qt.SizeHorCursor
            onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.LeftEdge) }
        }
        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 6 * root.dp
            cursorShape: Qt.SizeHorCursor
            onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.RightEdge) }
        }
        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 6 * root.dp
            cursorShape: Qt.SizeVerCursor
            onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.BottomEdge) }
        }
        MouseArea {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: 16 * root.dp
            height: 16 * root.dp
            cursorShape: Qt.SizeFDiagCursor
            onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge) }
        }
        MouseArea {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: 16 * root.dp
            height: 16 * root.dp
            cursorShape: Qt.SizeBDiagCursor
            onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.RightEdge | Qt.BottomEdge) }
        }
    }

    // ============================================================
    // ПАНЕЛЬ ПАРАМЕТРОВ (группы как .group в демо)
    // ============================================================
    Rectangle {
        id: params
        y: titleBar.height
        height: root.height - titleBar.height
        width: 304 * root.dp
        x: root.paramsOpen ? root.width - width : root.width
        color: "transparent"
        border.width: 0
        z: 40

        // backdrop: снимок контента под панелью + блюр (аналог backdrop-filter)
        ShaderEffectSource {
            id: drawerBackdrop
            anchors.fill: parent
            sourceItem: contentRow
            sourceRect: Qt.rect(params.x - contentRow.x, params.y - contentRow.y,
                                params.width, params.height)
            live: root.paramsOpen
            recursive: false
            visible: root.paramsOpen
        }
        MultiEffect {
            anchors.fill: parent
            source: drawerBackdrop
            blurEnabled: true
            blur: 1.0
            blurMax: 40
            visible: root.paramsOpen
        }
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(5 / 255, 10 / 255, 18 / 255, 0.92)
        }
        Behavior on x { NumberAnimation { duration: 300; easing.type: Easing.InOutCubic } }

        Rectangle {
            anchors.left: parent.left
            width: 1
            height: parent.height
            color: Qt.rgba(150 / 255, 190 / 255, 235 / 255, 0.16)
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ---------- шапка (52) ----------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 52 * root.dp

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 16 * root.dp
                    anchors.verticalCenter: parent.verticalCenter
                    text: "ПАРАМЕТРЫ ЧАТА"
                    color: "#9DB2CC"
                    font.family: root.fMono
                    font.pointSize: 9 * root.dp * 0.75
                    font.hintingPreference: Font.PreferNoHinting
                    font.letterSpacing: 1.6
                }
                Item {
                    anchors.right: parent.right
                    anchors.rightMargin: 14 * root.dp
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24 * root.dp
                    height: 24 * root.dp

                    IconImage {
                        anchors.centerIn: parent
                        name: "x"
                        iconSize: 12 * root.dp
                        tint: closeArea.containsMouse ? root.cIce : root.cText3
                    }
                    MouseArea {
                        id: closeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.paramsOpen = false
                    }
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: root.cLine
                }
            }

            // ---------- тело ----------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 16 * root.dp
                Layout.rightMargin: 16 * root.dp
                Layout.topMargin: 14 * root.dp
                spacing: 16 * root.dp

                // ===== ГЕНЕРАЦИЯ =====
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10 * root.dp

                    Text {
                        text: "ГЕНЕРАЦИЯ"
                        color: "#4F6076"
                        font.family: root.fMono
                        font.pointSize: 8 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        font.letterSpacing: 1.6
                    }

                    // температура
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6 * root.dp

                        RowLayout {
                            Layout.preferredHeight: 18 * root.dp
                            Layout.fillWidth: true
                            spacing: 6 * root.dp

                            Text {
                                text: "Температура"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredHeight: 18 * root.dp
                                Layout.preferredWidth: valueTemp.implicitWidth + 8 * root.dp
                                radius: 3 * root.dp
                                color: Qt.rgba(0.47, 0.65, 0.86, 0.10)
                                border.width: 1
                                border.color: Qt.rgba(0.59, 0.75, 0.92, 0.16)

                                Text {
                                    id: valueTemp
                                    anchors.centerIn: parent
                                    text: brain.temperature.toFixed(2)
                                    color: root.cIce2
                                    font.family: root.fMono
                                    font.pointSize: 9 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 0.45
                                }
                            }
                        }
                        NeuraSlider {
                            Layout.fillWidth: true
                            from: 0
                            to: 2
                            value: brain.temperature
                            onMoved: (v) => brain.temperature = v
                        }
                        RowLayout {
                            Layout.preferredHeight: 10 * root.dp
                            Layout.fillWidth: true
                            Text {
                                text: "ТОЧНО"
                                color: "#4A5B70"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1.05
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "СМЕЛО"
                                color: "#4A5B70"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1.05
                            }
                        }
                    }

                    // лимит ответа
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6 * root.dp

                        RowLayout {
                            Layout.preferredHeight: 18 * root.dp
                            Layout.fillWidth: true
                            spacing: 6 * root.dp

                            Text {
                                text: "Лимит ответа"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredHeight: 18 * root.dp
                                Layout.preferredWidth: valueLimit.implicitWidth + 8 * root.dp
                                radius: 3 * root.dp
                                color: Qt.rgba(0.47, 0.65, 0.86, 0.10)
                                border.width: 1
                                border.color: Qt.rgba(0.59, 0.75, 0.92, 0.16)

                                Text {
                                    id: valueLimit
                                    anchors.centerIn: parent
                                    text: root.fmtNum(brain.maxTokens > 0 ? brain.maxTokens : 8192)
                                    color: root.cIce2
                                    font.family: root.fMono
                                    font.pointSize: 9 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                    font.letterSpacing: 0.45
                                }
                            }
                        }
                        NeuraSlider {
                            Layout.fillWidth: true
                            from: 256
                            to: 8192
                            value: brain.maxTokens > 0 ? brain.maxTokens : 8192
                            onMoved: (v) => brain.maxTokens = Math.round(v)
                        }
                        RowLayout {
                            Layout.preferredHeight: 10 * root.dp
                            Layout.fillWidth: true
                            Text {
                                text: "256"
                                color: "#4A5B70"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1.05
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "ТОКЕНОВ"
                                color: "#4A5B70"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 1.05
                            }
                        }
                    }

                    // модель
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6 * root.dp

                        Text {
                            text: "Модель"
                            color: "#A9B8CC"
                            font.family: root.fSans
                            font.pointSize: 11.5 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32 * root.dp
                            radius: 6 * root.dp
                            color: Qt.rgba(0.55, 0.71, 0.90, 0.035)
                            border.width: 1
                            border.color: root.cLine

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 9 * root.dp
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.stubModel
                                color: "#DCE6F3"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            IconImage {
                                anchors.right: parent.right
                                anchors.rightMargin: 8 * root.dp
                                anchors.verticalCenter: parent.verticalCenter
                                name: "chevron"
                                iconSize: 14 * root.dp
                                tint: "#6E819B"
                            }
                        }
                        RowLayout {
                            spacing: 6 * root.dp
                            Rectangle {
                                Layout.preferredWidth: 3 * root.dp
                                Layout.preferredHeight: 3 * root.dp
                                radius: 1.5 * root.dp
                                color: root.cOk
                            }
                            Text {
                                text: "ЛОКАЛЬНО · 4-BIT"
                                color: "#4F6076"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 0.9
                            }
                        }
                    }
                }

                // ===== ГОЛОС =====
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: root.cLine
                    }
                    Item { Layout.preferredHeight: 16 * root.dp }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10 * root.dp

                        Text {
                            text: "ГОЛОС"
                            color: "#4F6076"
                            font.family: root.fMono
                            font.pointSize: 8 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 1.6
                        }
                        RowLayout {
                            Layout.preferredHeight: 18 * root.dp
                            Layout.fillWidth: true
                            spacing: 10 * root.dp

                            Text {
                                text: "Озвучивать ответы"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Item { Layout.fillWidth: true }
                            NeuraSwitch {
                                checked: root.stubVoice
                                onToggled: root.stubVoice = !root.stubVoice
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6 * root.dp

                            Text {
                                text: "Тембр"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32 * root.dp
                                radius: 6 * root.dp
                                color: Qt.rgba(0.55, 0.71, 0.90, 0.035)
                                border.width: 1
                                border.color: root.cLine

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 9 * root.dp
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.stubVoiceTone
                                    color: "#DCE6F3"
                                    font.family: root.fSans
                                    font.pointSize: 11.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                }
                                IconImage {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8 * root.dp
                                    anchors.verticalCenter: parent.verticalCenter
                                    name: "chevron"
                                    iconSize: 14 * root.dp
                                    tint: "#6E819B"
                                }
                            }
                        }
                    }
                }

                // ===== ПЕРСОНА =====
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: root.cLine
                    }
                    Item { Layout.preferredHeight: 14 * root.dp }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10 * root.dp

                        Text {
                            text: "ПЕРСОНА"
                            color: "#4F6076"
                            font.family: root.fMono
                            font.pointSize: 8 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 1.6
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 72 * root.dp
                            radius: 6 * root.dp
                            color: Qt.rgba(0.55, 0.71, 0.90, 0.035)
                            border.width: 1
                            border.color: root.cLine

                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 9 * root.dp
                                anchors.rightMargin: 9 * root.dp
                                anchors.topMargin: 7 * root.dp
                                anchors.bottomMargin: 7 * root.dp
                                text: "Ты — Нейра. Тёплая, внимательная, говоришь коротко и по делу."
                                wrapMode: Text.Wrap
                                color: "#B9C7DA"
                                font.family: root.fSans
                                font.pointSize: 11.2 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                lineHeight: 1.5
                                lineHeightMode: Text.ProportionalHeight
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 7 * root.dp
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 5 * root.dp
                                text: "78 / 2000"
                                color: "#46566B"
                                font.family: root.fMono
                                font.pointSize: 7.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                                font.letterSpacing: 0.75
                            }
                        }
                    }
                }

                // ===== ПАМЯТЬ =====
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: root.cLine
                    }
                    Item { Layout.preferredHeight: 12 * root.dp }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10 * root.dp

                        Text {
                            text: "ПАМЯТЬ"
                            color: "#4F6076"
                            font.family: root.fMono
                            font.pointSize: 8 * root.dp * 0.75
                            font.hintingPreference: Font.PreferNoHinting
                            font.letterSpacing: 1.6
                        }
                        RowLayout {
                            Layout.preferredHeight: 18 * root.dp
                            Layout.fillWidth: true
                            spacing: 10 * root.dp

                            Text {
                                text: "Помнить этот чат"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Item { Layout.fillWidth: true }
                            NeuraSwitch {
                                checked: root.stubMemory
                                onToggled: root.stubMemory = !root.stubMemory
                            }
                        }
                        RowLayout {
                            Layout.preferredHeight: 18 * root.dp
                            Layout.fillWidth: true
                            spacing: 10 * root.dp

                            Text {
                                text: "Предлагать темы"
                                color: "#A9B8CC"
                                font.family: root.fSans
                                font.pointSize: 11.5 * root.dp * 0.75
                                font.hintingPreference: Font.PreferNoHinting
                            }
                            Item { Layout.fillWidth: true }
                            NeuraSwitch {
                                checked: root.stubTopics
                                onToggled: root.stubTopics = !root.stubTopics
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // ---------- футер ----------
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: root.cLine
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 16 * root.dp
                Layout.rightMargin: 16 * root.dp
                Layout.topMargin: 10 * root.dp
                Layout.bottomMargin: 10 * root.dp
                spacing: 6 * root.dp

                Rectangle {
                    Layout.preferredHeight: 30 * root.dp
                    Layout.preferredWidth: resetLabel.implicitWidth + 22 * root.dp
                    radius: 5 * root.dp
                    color: Qt.rgba(0.55, 0.71, 0.90, 0.03)
                    border.width: 1
                    border.color: root.cLine

                    Text {
                        id: resetLabel
                        anchors.centerIn: parent
                        text: "Сбросить"
                        color: "#AEBBCD"
                        font.family: root.fSans
                        font.pointSize: 11 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            brain.temperature = 0.7
                            brain.maxTokens = 8192
                            root.stubVoice = true
                            root.stubMemory = true
                            root.stubTopics = false
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    Layout.preferredHeight: 30 * root.dp
                    Layout.preferredWidth: doneLabel.implicitWidth + 22 * root.dp
                    radius: 5 * root.dp
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#EAF2FF" }
                        GradientStop { position: 1.0; color: "#C3D9F8" }
                    }

                    Text {
                        id: doneLabel
                        anchors.centerIn: parent
                        text: "Готово"
                        color: "#05101f"
                        font.family: root.fSans
                        font.pointSize: 11 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        font.weight: Font.DemiBold
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.paramsOpen = false
                    }
                }
            }
        }
    }

    // ============================================================
    // МЕНЮ DEMO
    // ============================================================
    Popup {
        id: demoMenu
        x: root.width - width - 56 * root.dp
        y: 46 * root.dp
        width: 232 * root.dp
        height: 7 * 28 * root.dp + 12 * root.dp
        padding: 6 * root.dp
        background: Rectangle {
            color: "#070d16"
            radius: 9 * root.dp
            border.width: 1
            border.color: root.cLine2
        }

        Column {
            width: demoMenu.availableWidth
            spacing: 2

            Repeater {
                model: [
                    { key: "dialog",  label: "01   Диалог" },
                    { key: "stream",  label: "02   Генерация" },
                    { key: "empty",   label: "03   Пустой чат" },
                    { key: "link",    label: "04   Связь потеряна" },
                    { key: "long",    label: "05   Длинный ответ" },
                    { key: "params",  label: "06   Параметры" },
                    { key: "nostage", label: "07   Без сцены" }
                ]

                delegate: Rectangle {
                    width: parent.width
                    height: 28 * root.dp
                    radius: 5 * root.dp
                    color: itemArea.containsMouse ? Qt.rgba(0.55, 0.70, 0.90, 0.10) : "transparent"

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 8 * root.dp
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: "#C4D1E2"
                        font.family: root.fSans
                        font.pointSize: 11.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                    }
                    MouseArea {
                        id: itemArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.setDemoState(modelData.key)
                            demoMenu.close()
                        }
                    }
                }
            }
        }
    }

    // ============================================================
    // ДИАЛОГ СОХРАНЕНИЯ
    // ============================================================
    Popup {
        id: saveDialog
        modal: true
        dim: true
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        width: 380 * root.dp
        padding: 20 * root.dp

        background: Rectangle { color: root.cPanel; radius: 14 * root.dp; border.width: 1; border.color: root.cLine2 }

        ColumnLayout {
            spacing: 12 * root.dp

            Text {
                text: "Сохранить сессию"
                color: root.cText
                font.family: root.fSans
                font.pointSize: 15 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
                font.weight: Font.DemiBold
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 34 * root.dp
                radius: 8 * root.dp
                color: "#0b1220"
                border.width: 1
                border.color: sessionName.activeFocus ? root.cLine2 : root.cLine

                TextField {
                    id: sessionName
                    anchors.fill: parent
                    anchors.leftMargin: 10 * root.dp
                    anchors.rightMargin: 10 * root.dp
                    verticalAlignment: TextField.AlignVCenter
                    color: root.cText
                    placeholderText: "Имя сессии"
                    placeholderTextColor: root.cText4
                    font.family: root.fSans
                    font.pointSize: 12 * root.dp * 0.75
                    font.hintingPreference: Font.PreferNoHinting
                    background: Rectangle { color: "transparent" }
                    Keys.onReturnPressed: (event) => {
                        event.accepted = true
                        brain.saveSession(sessionName.text)
                        root.refreshSessions()
                        saveDialog.close()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8 * root.dp
                Item { Layout.fillWidth: true }
                Button {
                    text: "Отмена"
                    flat: true
                    contentItem: Text {
                        text: parent.text
                        color: root.cText3
                        font.family: root.fSans
                        font.pointSize: 11.5 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        horizontalAlignment: Text.AlignHCenter
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: saveDialog.close()
                }
                Rectangle {
                    Layout.preferredWidth: 100 * root.dp
                    Layout.preferredHeight: 30 * root.dp
                    radius: 5 * root.dp
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#EAF2FF" }
                        GradientStop { position: 1.0; color: "#C3D9F8" }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "Сохранить"
                        color: "#05101f"
                        font.family: root.fSans
                        font.pointSize: 11 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        font.weight: Font.DemiBold
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            brain.saveSession(sessionName.text)
                            root.refreshSessions()
                            saveDialog.close()
                        }
                    }
                }
            }
        }
    }

    // ============================================================
    // СВЯЗЬ С БЭКЕНДОМ
    // ============================================================
    Connections {
        target: brain

        function onTokenReceived(delta) {
            if (root.isThinking) {
                root.isThinking = false
                root.isPrinting = true
            }
            if (messages.count > 0) {
                var last = messages.get(messages.count - 1)
                if (last.role === "assistant") {
                    messages.setProperty(messages.count - 1, "text", last.text + delta)
                    view.ensureAtBottom()
                    return
                }
            }
            messages.append({ role: "assistant", text: delta, time: root.nowTime() })
            view.ensureAtBottom()
        }

        function onResponseFinished(full) {
            root.isThinking = false
            root.isPrinting = false
            if (messages.count > 0
                    && messages.get(messages.count - 1).role === "assistant") {
                if (full.length > 0) {
                    messages.setProperty(messages.count - 1, "text", full)
                } else {
                    messages.remove(messages.count - 1)
                }
            }
            view.ensureAtBottom()
        }

        function onSystemMessage(text) {
            root.isThinking = false
            root.isPrinting = false
            appendMessage("system", text)
        }

        function onHistoryLoaded(roles, texts) {
            messages.clear()
            for (var i = 0; i < roles.length; ++i) {
                messages.append({ role: roles[i], text: texts[i], time: "" })
            }
            view.scrollToBottomNow()
        }
    }

    Component.onCompleted: {
        root.refreshSessions()
        input.forceActiveFocus()
        if (messages.count === 0) {
            messages.append({ role: "assistant", text: "Привет! Я рядом. Можем вернуться к дизайну чата — или начать с чистого листа, как тебе удобнее.", time: "14:52", think: false })
            messages.append({ role: "user", text: "Помоги переделать экран чата. На широком мониторе справа пусто, а текст теряется на фоне.", time: "14:57", think: false })
            messages.append({ role: "assistant", text: "Тут две разные проблемы, и лечатся они по-разному.\n\n**Пустота справа** — это не про ширину, а про отсутствие второго слоя. У чата есть что показать рядом: присутствие, параметры, голос.\n\n**Текст «теряется»**, потому что панели полупрозрачные и арт просвечивает прямо под буквами.\n\n1. Арт получает свою сцену — он больше не служит фоном для текста.\n2. Диалог садится на плотную поверхность и держит контраст.\n3. Параметры уходят в панель, которая открывается по запросу.\n\nТак экран заполняется смыслом, а не декором. Оставляем?", time: "14:58", think: true })
        }
    }

    // ============================================================
    // СЛАЙДЕР
    // ============================================================
    // ============================================================
    // СТРОКИ РЕЙЛА
    // ============================================================
    component RailSection: RowLayout {
        id: sec
        property string num: ""
        property string title: ""

        Layout.topMargin: 6.8 * root.dp
        Layout.bottomMargin: 6 * root.dp
        spacing: 8 * root.dp

        Text {
            text: sec.num
            color: "#3E4E63"
            font.family: root.fMono
            font.pointSize: 8.5 * root.dp * 0.75
            font.hintingPreference: Font.PreferNoHinting
            font.letterSpacing: 1.4
        }
        Text {
            text: sec.title
            color: root.cText4
            font.family: root.fMono
            font.pointSize: 8.5 * root.dp * 0.75
            font.hintingPreference: Font.PreferNoHinting
            font.letterSpacing: 1.8
        }
        Rectangle {
            Layout.fillWidth: true
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: root.cLine }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }

    component RailChat: Rectangle {
        id: chat
        signal clicked()
        property string title: ""
        property string sub: ""
        property string time: ""
        property bool active: false

        Layout.preferredHeight: Math.round(43 * root.dp) - 3
        Layout.topMargin: Math.round(1 * root.dp)
        radius: 7 * root.dp
        color: chat.active ? "transparent"
                           : (chatArea.containsMouse ? Qt.rgba(0.55, 0.70, 0.90, 0.05) : "transparent")

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            visible: chat.active
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(0.47, 0.65, 0.86, 0.13) }
                GradientStop { position: 1.0; color: Qt.rgba(0.47, 0.65, 0.86, 0.04) }
            }
            border.width: root.pen
            border.color: Qt.rgba(0.59, 0.75, 0.92, 0.10)
        }

        Rectangle {
            visible: chat.active
            width: 1.5 * root.dp
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 8 * root.dp
            anchors.bottomMargin: 8 * root.dp
            radius: 1
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#EAF3FF" }
                GradientStop { position: 1.0; color: "#7FA8DC" }
            }
        }
        IconImage {
            anchors.left: parent.left
            anchors.leftMargin: 10 * root.dp
            anchors.verticalCenter: parent.verticalCenter
            name: "chat"
            iconSize: 13 * root.dp
            tint: chat.active ? root.cIce2 : root.cText4
        }
        Text {
            anchors.right: parent.right
            anchors.rightMargin: 10 * root.dp
            anchors.verticalCenter: parent.verticalCenter
            text: chat.time
            color: root.cText4
            font.family: root.fMono
            font.pointSize: 8.5 * root.dp * 0.75
            font.hintingPreference: Font.PreferNoHinting
            font.letterSpacing: 0.6
        }
        Column {
            anchors.left: parent.left
            anchors.leftMargin: 28 * root.dp
            anchors.right: parent.right
            anchors.rightMargin: 10 * root.dp
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 2.5 * root.dp
            spacing: 4 * root.dp

            Text {
                width: parent.width - 32 * root.dp
                text: chat.title
                elide: Text.ElideRight
                color: chat.active ? "#F1F6FD" : root.cText2
                font.family: root.fSans
                font.pointSize: 12.5 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                text: chat.sub
                elide: Text.ElideRight
                color: chat.active ? "#8FA2BC" : root.cText4
                font.family: root.fSans
                font.pointSize: 10.8 * root.dp * 0.75
                font.hintingPreference: Font.PreferNoHinting
            }
        }
        MouseArea {
            id: chatArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chat.clicked()
        }
    }

    // ============================================================
    // ТЕЛО СООБЩЕНИЯ (блочный рендер: абзац / заголовок / список / код)
    // ============================================================
    component MessageBody: Column {
        id: mb
        property string source: ""
        property color bodyColor: root.cBody
        property int baseSize: 14

        spacing: 10 * root.dp

        Repeater {
            model: root.parseBlocks(mb.source)

            delegate: Item {
                id: blockItem
                property var blk: modelData
                width: mb.width
                height: (blk.kind === "ol" || blk.kind === "ul")
                    ? listCol.implicitHeight + 2 * root.dp
                    : (blk.kind === "code" ? codeRect.height : textBlock.implicitHeight)

                Text {
                    id: textBlock
                    visible: blk.kind === "p" || blk.kind === "h"
                    width: parent.width
                    textFormat: Text.RichText
                    text: root.mdInline(blk.text || "")
                    color: mb.bodyColor
                    font.family: root.fSans
                    font.pixelSize: blk.kind === "h"
                        ? Math.round((blk.level === 1 ? 18 : blk.level === 2 ? 16 : 14) * root.fp)
                        : Math.round(mb.baseSize * root.fp)
                    font.weight: blk.kind === "h" ? Font.DemiBold : Font.Normal
                    lineHeight: 1.68
                    lineHeightMode: Text.ProportionalHeight
                    wrapMode: Text.WordWrap
                }

                Column {
                    id: listCol
                    visible: blk.kind === "ol" || blk.kind === "ul"
                    width: parent.width
                    spacing: 7 * root.dp

                    Repeater {
                        model: blk.items || []

                        delegate: Row {
                            width: listCol.width
                            spacing: 8 * root.dp

                            Rectangle {
                                visible: blk.kind === "ol"
                                width: 16 * root.dp
                                height: 16 * root.dp
                                radius: 4 * root.dp
                                color: Qt.rgba(0.47, 0.65, 0.86, 0.10)
                                border.width: 1
                                border.color: Qt.rgba(0.59, 0.75, 0.92, 0.20)

                                Text {
                                    anchors.centerIn: parent
                                    text: index + 1
                                    color: root.cIce2
                                    font.family: root.fMono
                                    font.pointSize: 8.5 * root.dp * 0.75
                                    font.hintingPreference: Font.PreferNoHinting
                                }
                            }
                            Rectangle {
                                visible: blk.kind === "ul"
                                width: 4 * root.dp
                                height: 4 * root.dp
                                radius: 2 * root.dp
                                color: root.cIce2
                                anchors.top: parent.top
                                anchors.topMargin: 9 * root.dp
                            }
                            Text {
                                width: parent.width - 24 * root.dp
                                textFormat: Text.RichText
                                text: root.mdInline(modelData)
                                color: mb.bodyColor
                                font.family: root.fSans
                                font.pixelSize: Math.round(mb.baseSize * root.fp)
                                lineHeight: 1.68
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
                    height: codeText.implicitHeight + 16 * root.dp
                    radius: 6 * root.dp
                    color: "#080d16"
                    border.width: 1
                    border.color: "#1a2433"

                    Text {
                        id: codeText
                        anchors.fill: parent
                        anchors.margins: 8 * root.dp
                        text: blk.text || ""
                        color: "#B9CBE0"
                        font.family: root.fMono
                        font.pointSize: 12 * root.dp * 0.75
                        font.hintingPreference: Font.PreferNoHinting
                        wrapMode: Text.NoWrap
                    }
                }
            }
        }
    }

    component MsgAction: Item {
        id: act
        property string kind: ""
        signal clicked()

        implicitWidth: 22 * root.dp
        implicitHeight: 22 * root.dp

        Rectangle {
            anchors.fill: parent
            radius: 5 * root.dp
            color: actArea.containsMouse ? Qt.rgba(0.62, 0.76, 0.92, 0.10) : "transparent"
        }
        IconImage {
            anchors.centerIn: parent
            name: act.kind === "voice" ? "volume" : act.kind
            iconSize: 13 * root.dp
            tint: actArea.containsMouse ? root.cIce : "#667A93"
        }
        MouseArea {
            id: actArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: act.clicked()
        }
    }

    // ============================================================
    // SVG-ИКОНКИ (точные пути из демо)
    // ============================================================
    component IconImage: Item {
        id: ico
        property string name: ""
        property color tint: "#AAC7EF"
        property real iconSize: 16

        // implicit, а не width/height: внутри RowLayout явный width «застывает»
        // на значении при старте и не растёт вместе с root.dp
        // (у Image implicit-размер только для чтения — поэтому обёртка Item)
        implicitWidth: iconSize
        implicitHeight: iconSize

        Image {
            anchors.fill: parent
            // SVG-символы демо (icons/svg, белые) — растр в точном размере, как в браузере
            source: "file:///D:/AI/neira-tools/qt_neira/icons/svg/" + ico.name + ".svg"
            sourceSize: Qt.size(Math.ceil(ico.iconSize), Math.ceil(ico.iconSize))
            fillMode: Image.PreserveAspectFit
            smooth: true
            layer.enabled: true
            layer.effect: MultiEffect {
                colorization: 1.0
                colorizationColor: ico.tint
            }
        }
    }

    component SvgIcon: Item {
        id: ico
        property string d: ""
        property real sw: 1.4
        property color color: "#AAC7EF"
        property bool filled: false

        implicitWidth: 24
        implicitHeight: 24

        Repeater {
            model: ico.d === "" ? [] : ico.d.split(" M").map(function (p, i) { return i === 0 ? p : "M" + p })

            Shape {
                width: 24
                height: 24
                preferredRendererType: Shape.CurveRenderer
                transform: Scale {
                    origin.x: 0
                    origin.y: 0
                    xScale: ico.width / 24
                    yScale: ico.height / 24
                }

                ShapePath {
                    fillColor: ico.filled ? ico.color : "transparent"
                    strokeColor: ico.filled ? "transparent" : ico.color
                    strokeWidth: ico.sw
                    capStyle: ShapePath.RoundCap
                    joinStyle: ShapePath.RoundJoin
                    PathSvg { path: modelData }
                }
            }
        }
    }

    component NeuraSwitch: Rectangle {
        id: sw
        property bool checked: false
        signal toggled()

        implicitWidth: 32 * root.dp
        implicitHeight: 18 * root.dp
        radius: 4 * root.dp
        color: sw.checked ? "#203045" : "#1a2433"
        border.width: 1
        border.color: sw.checked ? "#627A98" : "#2b3a4e"

        Rectangle {
            width: 12 * root.dp
            height: 12 * root.dp
            radius: 2 * root.dp
            // демо: border 1px + top/left 2px → 3 от края; вкл. — translateX(14)
            y: (sw.height - height) / 2
            x: sw.checked ? sw.width - width - 3 * root.dp : 3 * root.dp
            color: sw.checked ? "#EAF2FF" : "#8CA0B9"
            Behavior on x { NumberAnimation { duration: 160 } }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: sw.toggled()
        }
    }

    component NeuraSlider: Item {
        id: s
        property real from: 0
        property real to: 1
        property real value: 0
        signal moved(real v)

        implicitHeight: 20 * root.dp

        readonly property real ratio: (s.to > s.from)
            ? Math.max(0, Math.min(1, (s.value - s.from) / (s.to - s.from)))
            : 0

        Rectangle {
            id: track
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: 2 * root.dp
            radius: height / 2
            color: Qt.rgba(0.55, 0.70, 0.90, 0.16)
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: track.width * s.ratio
            height: track.height
            radius: track.height / 2
            color: root.cIce2
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            x: Math.max(0, Math.min(track.width - width, track.width * s.ratio - width / 2))
            width: 17 * root.dp
            height: 17 * root.dp
            radius: width / 2
            color: Qt.rgba(0.47, 0.65, 0.86, 0.14)
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            x: Math.max(0, Math.min(track.width - width, track.width * s.ratio - width / 2))
            width: 11 * root.dp
            height: 11 * root.dp
            radius: width / 2
            color: "#EAF2FF"
            border.width: 2 * root.dp
            border.color: "#6E9BD4"
        }
        MouseArea {
            anchors.fill: parent
            anchors.topMargin: -6 * root.dp
            anchors.bottomMargin: -6 * root.dp
            onPressed: (mouse) => setFromX(mouse.x)
            onPositionChanged: (mouse) => { if (pressed) setFromX(mouse.x) }

            function setFromX(px) {
                var r = Math.max(0, Math.min(1, px / width))
                s.moved(s.from + r * (s.to - s.from))
            }
        }
    }
}
