// Main.qml — окно Нейры: каркас, состояние, связь с brain (NeiraBrain, context property).
// Внешний вид и поведение элементов — в компонентах рядом: Theme, Header, Sidebar, ChatView, MessageBubble,
// Composer, StagePanel (+ NeiraAvatar), SettingsPanel, PcControl, PcConfirmCard.
// Запуск с аргументами для проверки вида: neira_qt.exe --size=1280x820 [--scene=...] (см. DemoScript.qml;
// сцены работают только при NEIRA_QT_DEMO=1).

import QtQuick
import QtQuick.Layouts

Window {
    id: root

    width: 1280
    height: 820
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "Нейра"
    color: Theme.bg
    flags: Qt.Window | Qt.FramelessWindowHint

    // ---------- аргументы командной строки (для проверки вида) ----------
    function arg(name, def) {
        var a = Qt.application.arguments
        for (var i = 0; i < a.length; ++i)
            if (a[i].indexOf("--" + name + "=") === 0) return a[i].substring(name.length + 3)
        return def
    }
    Component.onCompleted: {
        railOn = Theme.sidebarDocked                // в варианте b история выезжает по кнопке
        var sz = arg("size", "")
        if (sz.indexOf("x") > 0) {
            root.width = parseInt(sz.split("x")[0])
            root.height = parseInt(sz.split("x")[1])
        }
        brain.refreshHistory()
        composer.focusInput()
    }
    Binding { target: Theme; property: "winWidth"; value: root.width }

    // ---------- состояние UI ----------
    property bool isThinking: false
    property bool isPrinting: false
    property bool railOn: true
    property bool stageOn: true
    property bool settingsOpen: false
    property bool pcOpen: false
    property string chatTitle: "Новый разговор"
    property string demoActivity: ""              // подмена состояния для снимков
    property string demoActiveUid: ""
    property real demoMouth: -1
    property string demoEmotion: ""               // подмена эмоции для снимков
    property bool demoStill: false
    property real demoTilt: 0
    property real demoSway: 99
    property real demoBlink: 99
    property string demoPose: ""
    property real demoFlash: -1
    property real demoFlashT: 0.37
    property var allSessions: []
    property string sessionFilter: ""

    readonly property bool railShown: railOn && (Theme.sidebarDocked ? width >= 900 : true)
    readonly property bool stageShown: stageOn && width >= 1180
    readonly property real railW: Theme.px(264)
    readonly property real stageW: stageShown ? Math.min(Theme.px(900), Math.max(Theme.px(420), width * 0.36)) : 0

    readonly property string activity: demoActivity !== "" ? demoActivity
        : brain.recording ? "listening"
        : (brain.speaking || isPrinting) ? "speaking"
        : isThinking ? "thinking" : "idle"
    readonly property string stateText: activity === "listening" ? "слушает…"
        : activity === "thinking" ? "думает…"
        : activity === "speaking" ? "говорит…"
        : brain.connectionStatus === "connected" ? "на связи"
        : brain.connectionStatus === "failed" ? "нет связи"
        : "переподключение…" + (brain.reconnectAttempt > 0 ? " [" + brain.reconnectAttempt + "]" : "")

    // ---------- сообщения и разговоры ----------
    ListModel { id: messages }
    ListModel { id: sessionsModel }
    property alias messageModel: messages

    function nowTime() { return Qt.formatTime(new Date(), "HH:mm") }
    function dayKey(d) { return Qt.formatDate(d, "yyyy-MM-dd") }

    function appendMessage(role, text) {
        if (role === "system" && messages.count > 0) {
            var last = messages.get(messages.count - 1)
            if (last.role === "system" && last.text === text) return
        }
        messages.append({ role: role, text: text, time: nowTime(), day: dayKey(new Date()) })
        if (role === "user") chat.scrollToBottomNow(); else chat.ensureAtBottom()
    }

    // стоп до первого слова оставляет пустой пузырь Нейры — убираем его
    function dropBlankAssistant() {
        if (messages.count > 0) {
            var last = messages.get(messages.count - 1)
            if (last.role === "assistant" && last.text.trim() === "") messages.remove(messages.count - 1)
        }
    }

    function refreshSessions() {
        sessionsModel.clear()
        var f = sessionFilter.toLowerCase()
        for (var i = 0; i < allSessions.length; ++i) {
            var it = allSessions[i]
            if (f === "" || (it.title + " " + it.sub).toLowerCase().indexOf(f) >= 0)
                sessionsModel.append({ uid: it.uid, title: it.title, sub: it.sub })
        }
    }

    function send(t) {
        var hasFiles = brain.attachments.length > 0
        if (t.trim() === "" && !hasFiles) return
        if (t.trim() === "/new") { newChatUi(); return }
        var shown = t
        if (hasFiles) shown += (t === "" ? "" : "\n\n") + "[вложения: " + brain.attachments.join(", ") + "]"
        appendMessage("user", shown)
        isThinking = true
        isPrinting = false
        brain.sendMessage(t)
    }

    TextEdit { id: clipHelper; visible: false; width: 4; height: 4 }
    function copyMessage(t) {
        clipHelper.text = t
        clipHelper.selectAll()
        clipHelper.copy()
        appendMessage("system", "скопировано в буфер")
    }

    function regenerate() {
        if (brain.isGenerating) return
        if (messages.count > 0 && messages.get(messages.count - 1).role === "assistant")
            messages.remove(messages.count - 1)
        isThinking = true
        isPrinting = false
        brain.regenerate()
    }

    function stopGeneration() {
        brain.stop()
        isThinking = false
        isPrinting = false
    }

    function newChatUi() {
        if (brain.isGenerating) { appendMessage("system", "подожди — ответ ещё идёт"); return }
        messages.clear()
        brain.newChat()
        chatTitle = "Новый разговор"
        appendMessage("system", "Нейра здесь. О чём поговорим?")
        composer.focusInput()
    }

    function openChat(uid, title) {
        if (brain.isGenerating) { appendMessage("system", "подожди — ответ ещё идёт"); return }
        chatTitle = title
        brain.openHistory(uid)
        if (!Theme.sidebarDocked) railOn = false
    }

    function closeOverlays() { settingsOpen = false; pcOpen = false }

    // ---------- горячие клавиши ----------
    Shortcut { sequence: "F11"; onActivated: { if (root.visibility === Window.FullScreen) root.showNormal(); else root.showFullScreen() } }
    Shortcut { sequence: "Esc"; onActivated: { if (root.settingsOpen || root.pcOpen) root.closeOverlays(); else if (root.visibility === Window.FullScreen) root.showNormal() } }
    Shortcut { sequence: "Ctrl+N"; onActivated: root.newChatUi() }
    Shortcut { sequence: "Ctrl+K"; onActivated: { root.railOn = true; sidebar.focusSearch() } }

    // ============================================================
    // КАРКАС
    // ============================================================
    Rectangle { anchors.fill: parent; color: Theme.bg; z: -1000 }

    Header {
        id: header
        z: 100
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        win: root
        chatTitle: root.chatTitle
        activity: root.activity
        stateText: root.stateText
        sidebarOn: root.railOn
        stageOn: root.stageOn
        settingsOn: root.settingsOpen
        pcOpen: root.pcOpen
        compact: root.width < 1180
        onSidebarToggled: root.railOn = !root.railOn
        onStageToggled: root.stageOn = !root.stageOn
        onSettingsToggled: { root.pcOpen = false; root.settingsOpen = !root.settingsOpen }
        onPcToggled: { root.settingsOpen = false; root.pcOpen = !root.pcOpen }
    }

    Item {
        id: body
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right

        GridLayout {
            id: grid
            anchors.fill: parent
            anchors.leftMargin: Theme.sidebarDocked && root.railShown ? root.railW : 0
            Behavior on anchors.leftMargin { NumberAnimation { duration: Theme.dBase; easing.type: Easing.OutCubic } }
            rows: 1
            columns: 2
            columnSpacing: 0

            ColumnLayout {
                Layout.row: 0
                Layout.column: Theme.stageLeft ? 1 : 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                ChatView {
                    id: chat
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: messages
                    onCopyRequested: (t) => root.copyMessage(t)
                    onRegenerateRequested: root.regenerate()
                }
                Composer {
                    id: composer
                    Layout.fillWidth: true
                    Layout.preferredHeight: implicitHeight
                    win: root
                    onSendRequested: (t) => root.send(t)
                    onStopRequested: root.stopGeneration()
                }
            }

            StagePanel {
                id: stage
                Layout.row: 0
                Layout.column: Theme.stageLeft ? 0 : 1
                Layout.fillHeight: true
                Layout.preferredWidth: root.stageW
                Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.dBase; easing.type: Easing.OutCubic } }
                state: root.activity
                mouthLevel: root.demoMouth >= 0 ? root.demoMouth : brain.mouthLevel
                stateText: root.stateText
                emotion: root.demoEmotion !== "" ? root.demoEmotion : brain.emotion
                still: root.demoStill
                baseTilt: root.demoTilt
                swayFix: root.demoSway
                blinkFix: root.demoBlink
                poseFix: root.demoPose
                stress: brain.stress
                flashFix: root.demoFlash
                flashTime: root.demoFlashT
            }
        }

        // разговоры: в варианте a — закреплённая панель слева, в b — выезжающая поверх
        Rectangle {          // затемнение под выезжающей панелью
            anchors.fill: parent
            z: 20
            color: Theme.scrim
            opacity: !Theme.sidebarDocked && root.railOn ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.dBase } }
            MouseArea { anchors.fill: parent; onClicked: root.railOn = false }
        }
        Sidebar {
            id: sidebar
            z: 30
            width: root.railW
            height: parent.height
            x: root.railShown ? 0 : -width
            Behavior on x { NumberAnimation { duration: Theme.dBase; easing.type: Easing.OutCubic } }
            sessions: sessionsModel
            activeUid: root.demoActiveUid !== "" ? root.demoActiveUid : brain.activeHistory
            onNewChatRequested: { root.newChatUi(); if (!Theme.sidebarDocked) root.railOn = false }
            onOpenRequested: (uid, title) => root.openChat(uid, title)
            onRemoveRequested: (uid) => brain.deleteHistory(uid)
            onFilterChanged: (t) => { root.sessionFilter = t; root.refreshSessions() }
        }

        // карточка подтверждения действия Нейры на ПК — поверх всего, пока не отвечено
        PcConfirmCard {
            z: 90
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: composer.height + Theme.s5
        }
    }

    // ---------- затемнение и панель настроек ----------
    Rectangle {
        anchors.fill: body
        z: 40
        color: Theme.scrim
        opacity: root.settingsOpen ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: Theme.dBase } }
        MouseArea { anchors.fill: parent; onClicked: root.closeOverlays() }
    }
    SettingsPanel {
        id: settings
        z: 50
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        open: root.settingsOpen
        onCloseRequested: root.closeOverlays()
        onTopicRequested: {
            root.isThinking = true
            root.isPrinting = false
            brain.proactiveSpeak()
            root.closeOverlays()
        }
    }

    // ---------- «Управление ПК» ----------
    MouseArea {
        anchors.fill: body
        z: 70
        visible: root.pcOpen
        onClicked: root.pcOpen = false
    }
    PcControl {
        z: 80
        open: root.pcOpen
        x: root.width - width - Theme.s3
        y: header.height + Theme.s2
        onCloseRequested: root.pcOpen = false
    }

    // ---------- ресайз окна без рамки ----------
    Item {
        anchors.fill: parent
        z: 200
        enabled: root.visibility !== Window.Maximized
        MouseArea { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 6
            cursorShape: Qt.SizeHorCursor; onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.LeftEdge) } }
        MouseArea { anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 6
            cursorShape: Qt.SizeHorCursor; onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.RightEdge) } }
        MouseArea { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 6
            cursorShape: Qt.SizeVerCursor; onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.BottomEdge) } }
        MouseArea { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 16; height: 16
            cursorShape: Qt.SizeFDiagCursor; onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge) } }
        MouseArea { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 16; height: 16
            cursorShape: Qt.SizeBDiagCursor; onPressed: (m) => { if (m.button === Qt.LeftButton) root.startSystemResize(Qt.RightEdge | Qt.BottomEdge) } }
    }

    // ============================================================
    // СВЯЗЬ С БЭКЕНДОМ
    // ============================================================
    Connections {
        target: brain

        function onTokenReceived(delta) {
            if (root.isThinking) { root.isThinking = false; root.isPrinting = true }
            if (messages.count > 0) {
                var last = messages.get(messages.count - 1)
                if (last.role === "assistant") {
                    messages.setProperty(messages.count - 1, "text", last.text + delta)
                    chat.ensureAtBottom()
                    return
                }
            }
            messages.append({ role: "assistant", text: delta, time: root.nowTime(), day: root.dayKey(new Date()) })
            chat.ensureAtBottom()
        }

        function onResponseFinished(full) {
            root.isThinking = false
            root.isPrinting = false
            if (full.trim() === "") root.dropBlankAssistant()
            if (messages.count > 0 && messages.get(messages.count - 1).role === "assistant") {
                if (full.length > 0) messages.setProperty(messages.count - 1, "text", full)
                else messages.remove(messages.count - 1)
            } else if (full.length > 0) {
                messages.append({ role: "assistant", text: full, time: root.nowTime(), day: root.dayKey(new Date()) })
            }
            chat.ensureAtBottom()
        }

        function onSystemMessage(text) {
            root.isThinking = false
            root.isPrinting = false
            root.dropBlankAssistant()
            root.appendMessage("system", text)
        }

        function onHistoryLoaded(roles, texts, stamps) {
            messages.clear()
            for (var i = 0; i < roles.length; ++i) {
                if (texts[i].trim() === "") continue          // прерванный ответ без слов
                messages.append({ role: roles[i], text: texts[i],
                                 time: stamps[i].length >= 16 ? stamps[i].substring(11, 16) : "",
                                 day: stamps[i].length >= 10 ? stamps[i].substring(0, 10) : root.dayKey(new Date()) })
            }
            root.isThinking = false
            root.isPrinting = false
            chat.scrollToBottomNow()
        }

        function onHistoryListChanged(items) {
            root.allSessions = items
            root.refreshSessions()
        }

        function onHistoryDeleted(uid) {
            if (uid === brain.activeHistory) {
                messages.clear()
                root.chatTitle = "Новый разговор"
            }
        }

        function onUserTranscribed(text) {
            root.appendMessage("user", text)
            root.isThinking = true
            root.isPrinting = false
        }
    }

    // самопроверка на живой сборке: neira_qt.exe --autotest=<папка снимков> (см. AutoTest.qml)
    Loader {
        active: root.arg("autotest", "") !== ""
        source: "AutoTest.qml"
        onLoaded: { item.outDir = root.arg("autotest", ""); item.app = root }
    }

    // подача демо-данных и снимков (только NEIRA_QT_DEMO=1)
    Loader {
        active: brain.demoMode
        source: "DemoScript.qml"
        onLoaded: item.app = root
    }
}
