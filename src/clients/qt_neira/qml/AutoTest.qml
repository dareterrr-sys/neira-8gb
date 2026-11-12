// AutoTest.qml — самопроверка на живой сборке (запуск: neira_qt.exe --autotest=<папка для снимков>).
// Только со своим GPU.lock и поднятым стеком. Итог — строки «AUTOTEST …» в neira_qt.log.
import QtQuick

Item {
    id: at
    property var app: null
    property string outDir: ""
    property int step: 0
    property int ticks: 0               // по 0.5 с в текущем шаге
    property bool sawSpeaking: false
    property real maxMouth: 0
    property var created: []            // uid разговоров, созданных тестом
    property string firstAnswer: ""

    function log(s) { console.log("AUTOTEST " + s) }
    function shot(name) {
        app.contentItem.grabToImage(function (r) { r.saveToFile(outDir + "/" + name + ".png") })
    }
    function next() { step++; ticks = 0 }
    function lastText() { var m = app.messageModel; return m.count ? m.get(m.count - 1).text : "" }
    function lastRole() { var m = app.messageModel; return m.count ? m.get(m.count - 1).role : "" }
    function trackUid() { var u = brain.activeHistory; if (u && created.indexOf(u) < 0) created.push(u) }

    onAppChanged: if (app) { app.railOn = false; run.start() }

    Connections {
        target: brain
        function onSpeakingChanged() { if (brain.speaking) at.sawSpeaking = true }
        function onMouthLevelChanged() { if (brain.mouthLevel > at.maxMouth) at.maxMouth = brain.mouthLevel }
    }

    Timer {
        id: run
        interval: 500
        repeat: true
        onTriggered: {
            at.ticks++
            switch (at.step) {
            case 0:   // связь
                if (brain.connectionStatus === "connected" && brain.brainUp) {
                    at.log("1 связь: ok (ws connected, brain up, voice up=" + brain.voiceUp + ", voiceEnabled=" + brain.voiceEnabled + ")")
                    at.shot("live-1-idle"); at.next()
                } else if (at.ticks > 120) { at.log("1 связь: FAIL тайм-аут"); Qt.quit() }
                break
            case 1:   // вопрос → ответ
                if (at.ticks === 1) { app.send("Сколько будет 17 умножить на 23? Ответь коротко."); at.log("2 вопрос отправлен") }
                if (at.ticks === 20) at.shot("live-2-thinking")
                if (brain.speaking && at.ticks % 6 === 0 && !at.firstAnswer) at.shot("live-3-speaking")
                if (at.ticks > 4 && !brain.isGenerating && lastRole() === "assistant" && lastText() !== "") {
                    at.firstAnswer = lastText(); at.trackUid()
                    at.log("2 ответ: «" + at.firstAnswer.substring(0, 120) + "» speaking=" + at.sawSpeaking + " maxMouth=" + at.maxMouth.toFixed(2))
                    at.shot("live-4-answer"); at.next()
                } else if (at.ticks > 360) { at.log("2 ответ: FAIL тайм-аут"); at.next() }
                break
            case 2:   // стоп во время озвучки/генерации
                if (at.ticks === 1) { at.sawSpeaking = false; app.send("Расскажи подробно, не меньше десяти предложений, про историю шахмат."); at.log("3 длинный вопрос отправлен") }
                if (at.ticks > 4 && (brain.speaking || lastText().length > 60) && brain.isGenerating) {
                    var t0 = Date.now(); app.stopGeneration(); at.log("3 стоп нажат, isGenerating сразу после=" + brain.isGenerating)
                    at.shot("live-5-stop"); at.ticks = 1000; at.next()
                } else if (at.ticks > 240) { at.log("3 стоп: FAIL ответ не начался"); app.stopGeneration(); at.next() }
                break
            case 3:
                if (at.ticks > 8) { at.log("3 после стопа: isGenerating=" + brain.isGenerating + " speaking=" + brain.speaking); at.trackUid(); at.next() }
                break
            case 4:   // загрузка разговора = память
                if (at.ticks === 1) {
                    var uid = brain.activeHistory
                    app.chatTitle = "тест"; brain.openHistory(uid); at.log("4 открыт разговор " + uid)
                }
                if (at.ticks === 10) { app.send("Что я спросил у тебя в самом начале разговора? Назови числа."); }
                if (at.ticks > 14 && !brain.isGenerating && lastRole() === "assistant" && at.ticks > 12) {
                    at.log("4 память: «" + lastText().substring(0, 160) + "»"); at.shot("live-6-memory"); at.next()
                } else if (at.ticks > 360) { at.log("4 память: FAIL тайм-аут"); at.next() }
                break
            case 5:   // экраны: история, настройки, ПК
                if (at.ticks === 1) { app.railOn = true }
                if (at.ticks === 5) at.shot("live-7-history")
                if (at.ticks === 7) { app.railOn = false; app.settingsOpen = true }
                if (at.ticks === 12) at.shot("live-8-settings-nejra")
                if (at.ticks === 14) { app.contentItem.children.forEach(function (c) { if (c.tab !== undefined && c.topicRequested !== undefined) c.tab = 1 }) }
                if (at.ticks === 18) at.shot("live-9-settings-system")
                if (at.ticks === 20) { app.settingsOpen = false; app.pcOpen = true }
                if (at.ticks === 25) { at.log("5 pcAvailable=" + brain.pcAvailable + " pcEnabled=" + brain.pcEnabled); at.shot("live-10-pc") }
                if (at.ticks === 28) { app.pcOpen = false; at.next() }
                break
            case 6:   // уборка: удалить созданные тестом и 3 старых тестовых (10.11 06:13/06:21/06:26)
                if (at.ticks === 1) {
                    var del = at.created.slice()
                    var all = app.allSessions
                    for (var i = 0; i < all.length; ++i)
                        if (/^10\.11\s+06:(13|21|26)$/.test(all[i].title.trim()) && del.indexOf(all[i].uid) < 0) del.push(all[i].uid)
                    at.log("6 удаляю " + del.length + " тестовых разговоров")
                    at.toDelete = del
                }
                if (at.ticks >= 1 && at.toDelete && at.toDelete.length > 0 && at.ticks % 2 === 0) brain.deleteHistory(at.toDelete.shift())
                if (at.ticks > 4 && at.toDelete.length === 0) { at.log("6 удаление отправлено, осталось в списке " + app.allSessions.length); at.next() }
                break
            default:
                if (at.ticks > 6) { at.log("ГОТОВО"); Qt.quit() }
            }
        }
    }
    property var toDelete: null
}
