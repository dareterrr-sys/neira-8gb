// DemoScript.qml — демо-данные и снимки окна для проверки вида. Грузится только при NEIRA_QT_DEMO=1.
// Аргументы: --scene=main|settings1|settings2|history|pc|confirm|speaking  --shot=<путь.png>  --delay=<мс>
import QtQuick

Item {
    id: demo
    property var app: null

    function inject(o) { brain.debugInject(JSON.stringify(o)) }

    onAppChanged: if (app) Qt.callLater(setup)

    function setup() {
        var scene = app.arg("scene", "main")
        app.allSessions = [
            { uid: "d1", title: "10.11  09:42", sub: "Объясни, как работает рекурсия" },
            { uid: "d2", title: "09.11  21:15", sub: "Помоги с письмом в деканат" },
            { uid: "d3", title: "09.11  13:02", sub: "Что нового в Qt 6.8?" },
            { uid: "d4", title: "07.11  18:30", sub: "Рецепт ужина на двоих" }
        ]
        app.refreshSessions()
        app.demoActiveUid = "d1"
        app.chatTitle = "Объясни, как работает рекурсия"
        var m = app.messageModel
        var today = app.dayKey(new Date()), yday = app.dayKey(new Date(Date.now() - 86400000))
        m.clear()
        m.append({ day: yday, role: "user", text: "Объясни, как работает рекурсия, только без занудства.", time: "09:42" })
        m.append({ day: yday, role: "assistant", time: "09:42",
            text: "Рекурсия — это когда функция решает задачу, вызывая саму себя на задаче поменьше.\n\n"
                + "Нужны всего две вещи:\n- **база** — случай, где ответ известен сразу;\n- **шаг** — сведение задачи к такой же, но меньшей.\n\n"
                + "Например, факториал:\n```\ndef fact(n):\n    return 1 if n <= 1 else n * fact(n - 1)\n```\n"
                + "Подробнее — на [странице учебника](https://example.com) или https://example.com/doc_1/page." })
        m.append({ day: today, role: "user", text: "А если забыть базу?", time: "09:43" })
        m.append({ day: today, role: "system", text: "Нейра думает над ответом", time: "09:43" })
        m.append({ day: today, role: "assistant", time: "09:43",
            text: "Тогда функция будет вызывать себя бесконечно, пока не кончится стек — получишь переполнение." })
        app.chatTitle = "Объясни, как работает рекурсия"

        if (scene === "settings1") { app.settingsOpen = true }
        else if (scene === "settings2") { app.settingsOpen = true; settingsTab() }
        else if (scene === "history") { app.railOn = true }
        else if (scene === "speaking") { app.demoActivity = "speaking"; app.demoMouth = 0.7 }
        else if (scene === "thinking") { app.demoActivity = "thinking" }
        else if (scene === "pc" || scene === "confirm") {
            inject({ type: "pc-control-status", enabled: true, reason: "" })
            inject({ type: "pc-control-action", kind: "open", desc: "Открыла Блокнот" })
            app.pcOpen = (scene === "pc")
            if (scene === "confirm") {
                inject({ type: "pc-control-confirm-request", id: "demo1",
                         action: "Нажать «Сохранить» в окне «Блокнот»", reason: "Нужно сохранить файл заметки." })
            }
        }
        else if (scene === "pcoff") { app.pcOpen = true }

        if (app.arg("mouth", "") !== "") { app.demoActivity = "speaking"; app.demoMouth = parseFloat(app.arg("mouth", "0")) }   // рот под звук: 0.1 line, 0.4 o, 0.6 ie, 0.9 a
        if (app.arg("emo", "") !== "") app.demoEmotion = app.arg("emo", "")
        if (app.arg("still", "") === "1") app.demoStill = true
        if (app.arg("sway", "") !== "") app.demoSway = parseFloat(app.arg("sway", "0"))
        if (app.arg("blink", "") !== "") app.demoBlink = parseFloat(app.arg("blink", "0"))
        if (app.arg("tilt", "") !== "") app.demoTilt = parseFloat(app.arg("tilt", "0"))
        if (app.arg("pose", "") !== "") app.demoPose = app.arg("pose", "")   // breath,yaw,roll,nod (снимки позы головы)
        if (app.arg("stress", "") !== "") inject({ type: "neira-stress", level: parseFloat(app.arg("stress", "0")), reason: "тест" })   // «сбой голограммы»: уровень 0..1
        if (app.arg("flash", "") !== "") { var fl = app.arg("flash", "").split(","); app.demoFlash = parseFloat(fl[0]); if (fl.length > 1) app.demoFlashT = parseFloat(fl[1]) }   // удержать вспышку: сила[,время]
        if (app.arg("stats", "") !== "") { var st = app.arg("stats", "").split(","); inject({ type: "neira-stats", tok_s: parseFloat(st[0]), tokens: parseInt(st[1]), ctx_tokens: parseInt(st[2]) }) }   // скорость,токенов,в разговоре
        if (app.arg("label", "") !== "") brain.setEmotionLabel(app.arg("label", ""))   // метка сервера → лицо (проверка таблицы)
        if (app.arg("labeltest", "") !== "") {   // все 8 меток подряд → файл (нужна QML_XHR_ALLOW_FILE_WRITE=1)
            var labs = ["neutral", "anger", "disgust", "fear", "joy", "smirk", "sadness", "surprise"], out = ""
            for (var i = 0; i < labs.length; ++i) { brain.setEmotionLabel("neutral"); brain.setEmotionLabel(labs[i]); out += labs[i] + " -> " + brain.emotion + "|" }
            brain.setEmotionLabel("bogus"); out += "bogus (лицо не меняется) -> " + brain.emotion + "|"
            var x = new XMLHttpRequest(); x.open("PUT", "file:///" + app.arg("labeltest", "")); x.send(out)
        }
        var shot = app.arg("shot", "")
        if (shot !== "") {
            shotTimer.path = shot
            shotTimer.interval = parseInt(app.arg("delay", "1500"))
            shotTimer.start()
        }
    }

    function settingsTab() {
        var p = app.children
        // вкладка «Система» выбирается свойством панели; ищем её среди детей окна
        for (var i = 0; i < app.contentItem.children.length; ++i) {
            var c = app.contentItem.children[i]
            if (c.tab !== undefined && c.topicRequested !== undefined) c.tab = 1
        }
    }

    Timer {
        id: shotTimer
        property string path: ""
        repeat: false
        onTriggered: demo.app.contentItem.grabToImage(function (r) {
            r.saveToFile(path)
            Qt.quit()
        })
    }
}
