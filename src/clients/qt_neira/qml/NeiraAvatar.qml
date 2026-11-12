// NeiraAvatar.qml — живая Нейра из 55 слоёв (риг отдела model-2d, слои и координаты — avatar/layers.json → LayersData.js).
//
// API (не менять — на него опирается StagePanel):
//   state:      "idle" | "listening" | "thinking" | "speaking"
//   mouthLevel: 0..1 — громкость проигрываемого сейчас звука (brain.mouthLevel); рот двигается только при state "speaking"
//   emotion:    ключ эмоции "01".."15" из layers.json либо старое имя ("neutral" | "smile" | "think" | "surprise" |
//               "sad" | "shy"); неизвестное → спокойная "01". Из ответа мозга: brain.emotion (метка [joy] и т. п. → лицо, см. NeiraBrain::setEmotionLabel).
// Слои — в 2× на холсте 1664×2512; сцена масштабируется целиком (stage.scale).
import QtQuick
import "avatar/LayersData.js" as LD

Item {
    id: av
    property string state: "idle"
    property real mouthLevel: 0
    property string emotion: "neutral"
    property real stress: 0            // уровень перегрузки 0..1 из сообщения сервера neira-stress (brain.stress); ≥ 0,7 — «сбой голограммы»
    readonly property bool overload: stress >= 0.7
    property real flashFix: -1         // снимки: >= 0 — удержать вспышку сбоя с такой силой (0..1), время — flashTime
    property real flashTime: 0.37
    property bool still: false         // снимки: покой без анимации (t=0)
    property real swayFix: 99          // снимки: зафиксировать качание (-0.6..0.6); 99 — не фиксировать
    onSwayFixChanged: if (swayFix < 90) sway = swayFix
    property bool hideBody: false      // снимки: скрыть всё, кроме частей головы (poseFix, 5-е поле = 1)
    property string poseFix: ""        // снимки: "breath,yaw,roll,nod" — зафиксировать позу головы (вместе с still=1)
    onPoseFixChanged: { var p = poseFix.split(","); if (p.length >= 5) hideBody = p[4] === "1"
        if (p.length >= 4) { breath = parseFloat(p[0]); yaw = parseFloat(p[1]); roll = parseFloat(p[2]); nod = parseFloat(p[3]) } }
    // статичный поворот всей фигуры: ось «середина подошв (827,2512) → середина между радужками (890,6; 468)» в full_2x.png
    // наклонена на 1,78° вправо; компенсируем (model-2d, штаб 11.11). Качание идёт поверх, симметрично.
    property real baseTilt: 0

    clip: true

    readonly property var dat: LD.data
    readonly property var emoAlias: ({ "neutral": "01", "smile": "13", "think": "08", "surprise": "07", "shy": "10", "sad": "11" })
    readonly property string emo: {
        var e = String(emotion)
        if (dat.emotions[e]) return e
        return emoAlias[e] || dat.default_emotion
    }

    // ---- анимационные величины ----
    property real tsec: 0
    property real breath: 0
    property real sway: 0
    property real yaw: 0
    property real blink: blinkFix <= 1 ? blinkFix : 0
    property real blinkFix: 99      // тест: 0..1 — зафиксировать моргание (демо --blink=)
    property real mouth: 0          // сглаженный mouthLevel
    property real roll: 0
    property real nod: 0

    function lay(n) { for (var i = 0; i < dat.layers.length; i++) if (dat.layers[i].name === n) return dat.layers[i]; return null }
    function src(e) { return Qt.resolvedUrl("avatar/" + e.file) }
    function visKey(m) { return m < 0.25 ? "line" : (m < 0.5 ? "o" : (m < 0.75 ? "ie" : "a")) }

    // слой с поворотом вокруг pivot
    component Spr: Image {
        property var lyr
        property real rot: 0
        source: lyr ? av.src(lyr) : ""
        x: lyr ? lyr.x : 0; y: lyr ? lyr.y : 0; z: lyr ? lyr.z : 0
        smooth: true; mipmap: true
        transform: Rotation { origin.x: lyr ? lyr.pivot[0] - lyr.x : 0; origin.y: lyr ? lyr.pivot[1] - lyr.y : 0; angle: rot }
    }

    // слот лица: при смене слоя старое изображение гаснет, новое проявляется за `fade` мс
    component Slot: Item {
        id: slot
        property var lyr
        property real fade: 120
        property real level: 1          // общая непрозрачность слота
        property var prev: null
        z: lyr ? lyr.z : 0
        opacity: level
        onLyrChanged: {
            if (!lyr) return
            oldImg.source = curImg.source
            oldImg.x = curImg.x; oldImg.y = curImg.y
            curImg.source = av.src(lyr); curImg.x = lyr.x; curImg.y = lyr.y
            xfade.restart()
        }
        Image { id: oldImg; smooth: true; mipmap: true; opacity: 0 }
        Image { id: curImg; smooth: true; mipmap: true; source: slot.lyr ? av.src(slot.lyr) : ""; x: slot.lyr ? slot.lyr.x : 0; y: slot.lyr ? slot.lyr.y : 0 }
        ParallelAnimation {
            id: xfade
            NumberAnimation { target: oldImg; property: "opacity"; from: 1; to: 0; duration: slot.fade }
            NumberAnimation { target: curImg; property: "opacity"; from: 0; to: 1; duration: slot.fade }
        }
    }


    // ---- сцена 1664×2512, вписана в панель по высоте и ширине корпуса ----
    Item {
        id: stage
        width: 1664; height: 2512
        readonly property real sc: Math.min(av.height / 2512, av.width / 1180)
        scale: sc
        transformOrigin: Item.TopLeft
        // корпус занимает x 388..1412 (центр 900); ставим по центру панели, чуть вправо
        x: av.width / 2 - 900 * sc
        y: 0
        Item {   // фигура целиком: статичный наклон baseTilt вокруг точки между подошвами
            id: fig; anchors.fill: parent
            transform: Rotation { origin.x: 827; origin.y: 2512; angle: -av.baseTilt }

        // наклон в поясе (torso_tilt): верх (торс, шея, голова, коса, слоты лица, антенны) — один поворот вокруг pivot
        // пояса на угол для 50 px (голова на 50 px левее), ноги неподвижны
        readonly property var tt: av.dat.torso_tilt
        readonly property real tiltDeg: tt.deg_for_50px

        Spr { lyr: av.lay("legs"); visible: !av.hideBody }   // неподвижны

        Item {   // всё, что наклоняется в поясе
            id: tiltG; anchors.fill: parent; z: 10
            transform: Rotation { origin.x: fig.tt.pivot[0]; origin.y: fig.tt.pivot[1]; angle: fig.tiltDeg }

            // торс и коса справа (дыхание)
            Item {
                id: bodyG; anchors.fill: parent; z: 10; visible: !av.hideBody
                transform: Scale { origin.x: 880; origin.y: 1400; yScale: 1 + av.breath * 0.012 }
                Spr { lyr: av.lay("torso") }
                Spr { lyr: av.lay("braid") }   // коса ОДНИМ слоем (задача 10): не качается сама, движется только с торсом (дыхание, наклон в поясе)
            }
            Spr { lyr: av.lay("neck"); visible: !av.hideBody; y: (lyr ? lyr.y : 0) + av.breath * -2 }
            // голова: дыхание, yaw, наклон, кивок
            Item {
                id: headG; anchors.fill: parent; z: 30
                y: av.breath * -3 + av.nod; x: av.yaw * 10
                transform: Rotation { origin.x: 884; origin.y: 632; angle: av.yaw * 3 + av.roll }
                Spr { lyr: av.lay("head") }
                Spr { lyr: av.lay("sideL") }   // жёстко с головой (задача 12): качание убрано — под ним оставалась старая копия волос в head
                Spr { lyr: av.lay("sideR") }
                Spr { lyr: av.lay("phones") }
                Item {
                    width: 1664; height: 2512; z: 34.5
                    Slot { lyr: av.dat.face_slots.face[av.emo]; z: 0 }
                    Slot { lyr: av.dat.face_slots.blink[av.emo]; z: 0.5; level: av.blink }
                    Slot { lyr: av.dat.face_slots.mouth[av.emo]; z: 1; fade: 120; level: av.mouth > 0.05 ? 0 : 1 }
                    Slot { lyr: av.dat.face_slots.viseme[av.visKey(av.mouth)]; z: 2; fade: 60; level: av.mouth > 0.05 ? 1 : 0 }
                }
                Item {
                    width: 1664; height: 2512; z: 44
                    Spr { lyr: av.lay("antL"); z: 0; rot: Math.sin(av.tsec * 2.1) * (av.state === "thinking" ? 1.0 : 0.6) }   // только малое качание основания, ≤ 1°
                    Spr { lyr: av.lay("antR"); z: 0; rot: Math.sin(av.tsec * 2.4 + 1) * (av.state === "thinking" ? 1.0 : 0.6) }
                    Spr { lyr: av.lay("bangs"); z: 1 }
                }
            }
        }
        }
    }

    // ---- «сбой голограммы» (задача 13): короткие вспышки раз в 1–3 с при stress ≥ 0,7; в покое — ни таймеров, ни шейдера ----
    property real gate: overload ? 1 : 0
    Behavior on gate { NumberAnimation { duration: 1000 } }   // при stress < 0,7 вспышки затухают за 1 с
    property real flashEnv: 0
    property real flashEl: 0
    property real flashDur: 0.5
    property real flashClock: 0
    Timer {   // следующая вспышка; работает только пока перегрузка
        id: nextFlash
        interval: 1500
        running: av.overload && av.visible && av.width > 0 && !av.still && av.flashFix < 0
        repeat: true
        onTriggered: {
            av.flashDur = 0.3 + Math.random() * 0.5
            av.flashEl = 0
            flashDrv.running = true
            interval = 1000 + Math.random() * 2000
        }
    }
    Timer {   // ход вспышки; останавливается сам
        id: flashDrv
        interval: 33
        repeat: true
        onTriggered: {
            av.flashEl += 0.033; av.flashClock += 0.033
            if (av.flashEl >= av.flashDur) { av.flashEnv = 0; running = false }
            else av.flashEnv = Math.sin(Math.PI * av.flashEl / av.flashDur)
        }
    }
    readonly property real glitchAmt: flashFix >= 0 ? flashFix : flashEnv * gate
    Loader {
        id: glitchL
        z: 4
        active: av.glitchAmt > 0.001
        sourceComponent: Item {
            x: stage.x; y: 0; width: 1664; height: 2512
            scale: stage.sc; transformOrigin: Item.TopLeft
            ShaderEffect {
                anchors.fill: parent
                property variant src: ShaderEffectSource {
                    sourceItem: stage; hideSource: true; live: true
                    textureSize: Qt.size(Math.max(64, 1664 * stage.sc), Math.max(64, 2512 * stage.sc))
                }
                property real amt: av.glitchAmt
                property real time: av.flashFix >= 0 ? av.flashTime : av.flashClock
                property real lvl: Math.max(0, Math.min(1, (av.stress - 0.7) / 0.3))
                property real splitUv: (2 + 4 * lvl) / Math.max(1, 1664 * stage.sc)   // 2..6 px на экране
                property real bandShift: 0.03
                property real lineAmt: 1
                property real rows: 2512 * stage.sc / 3
                fragmentShader: Qt.resolvedUrl("avatar/glitch.frag.qsb")
            }
        }
    }

    // затемнение краёв: сцена мягко уходит в фон окна
    Rectangle {
        anchors.fill: parent
        z: 5
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.00; color: Theme.veil(0.95) }
            GradientStop { position: 0.10; color: Theme.veil(0.55) }
            GradientStop { position: 0.30; color: Theme.veil(0.0) }
        }
    }
    Rectangle {
        anchors.fill: parent
        z: 5
        gradient: Gradient {
            GradientStop { position: 0.00; color: Theme.veil(0.30) }
            GradientStop { position: 0.12; color: Theme.veil(0.0) }
            GradientStop { position: 0.80; color: Theme.veil(0.0) }
            GradientStop { position: 1.00; color: Theme.veil(0.94) }
        }
    }

    // ореол состояния: кольцо внизу сцены, цвет и ритм зависят от state, размер — от mouthLevel
    Item {
        id: halo
        z: 6
        width: Theme.px(150); height: width
        anchors.left: parent.left
        anchors.leftMargin: Theme.s5
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(64)
        visible: av.width > Theme.px(160)
        opacity: av.state === "idle" ? 0.0 : 0.9
        Behavior on opacity { NumberAnimation { duration: Theme.dBase } }

        property real breathe: 0
        SequentialAnimation on breathe {
            running: halo.visible && av.state !== "idle"
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 1; duration: av.state === "thinking" ? 700 : 2400; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0; duration: av.state === "thinking" ? 700 : 2400; easing.type: Easing.InOutSine }
        }
        readonly property real k: av.state === "speaking" ? av.mouthLevel : (av.state === "idle" ? 0.2 * breathe : 0.5 * breathe)

        Rectangle {
            anchors.centerIn: parent
            width: parent.width * (0.70 + 0.30 * halo.k)
            height: width
            radius: width / 2
            color: "transparent"
            border.width: Theme.px(2)
            border.color: av.state === "listening" ? Theme.ok : (av.state === "thinking" ? Theme.accent : Theme.lav)
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 0.46
            height: width
            radius: width / 2
            color: Theme.lavA(0.10 + 0.25 * halo.k)
        }
    }

    // ---- ход анимации (30 кадров/с; стоит, пока окно не видно) ----
    Timer {
        interval: 33
        running: av.visible && av.width > 0 && !av.still
        repeat: true
        onTriggered: {
            av.tsec += 0.033
            var t = av.tsec, st = av.state
            av.breath = Math.sin(t * (st === "speaking" ? 1.9 : 1.6)) * 0.5 + 0.5
            av.sway = av.swayFix < 90 ? av.swayFix : Math.sin(t * 0.9) * 0.6
            av.yaw = Math.sin(t * (st === "thinking" ? 0.7 : 0.4)) * (st === "thinking" ? 0.9 : 0.5)
            // моргание раз в ~3,2 с (в «слушает» чуть реже)
            var bp = t % (st === "listening" ? 4.4 : 3.2)
            av.blink = av.blinkFix <= 1 ? av.blinkFix : (bp < 0.16 ? Math.sin(bp / 0.16 * Math.PI) : 0)
            // рот: настоящий уровень звука, сглаженный; вне речи закрывается
            var target = st === "speaking" ? av.mouthLevel : 0
            av.mouth += (target - av.mouth) * 0.5
            if (av.mouth < 0.02) av.mouth = 0
            // голова: слушает — лёгкий наклон; говорит — кивок в такт голосу
            var rollT = st === "listening" ? -2.5 : (st === "thinking" ? 1.5 : 0)
            av.roll += (rollT - av.roll) * 0.1
            av.nod += ((st === "speaking" ? av.mouth * 3 : 0) - av.nod) * 0.3
        }
    }
}
