pragma Singleton
// Theme.qml — единственный источник цветов, шрифтов, отступов, радиусов и длительностей.
// Палитра — из образа Нейры (model-2d/образ.md): тёмно-синий, лаванда, тонкое золото.
// Масштаб автора сохранён: при ширине окна >= 2300 px интерфейс x1.25 (dp), чат x1.15 (fp).
import QtQuick

QtObject {
    id: t

    // ---------- вариант оформления (a — «Лавандовая ночь», b — «Золотая линия») ----------
    // выбран оформительский вариант «Золотая линия» (автор, 10.11.2026), сцена справа
    readonly property bool isA: false

    // ---------- масштаб ----------
    property real winWidth: 1280                 // выставляет Main.qml
    readonly property real dp: winWidth >= 2300 ? 1.25 : (winWidth >= 1900 ? 1.08 : 1.0)
    readonly property real fp: 1.0 + (dp - 1.0) * 0.6        // чат: 1.15 при dp 1.25
    readonly property real pen: dp >= 1.2 ? 1.2 : 1.0
    function px(n) { return n * dp }             // размер элемента
    function pt(n) { return n * dp * 0.75 }      // pointSize интерфейса по «дизайн-пикселям»
    function cpt(n) { return n * fp * 0.75 }     // pointSize чата

    // ---------- сетка 4/8 ----------
    readonly property real s1: 4 * dp
    readonly property real s2: 8 * dp
    readonly property real s3: 12 * dp
    readonly property real s4: 16 * dp
    readonly property real s5: 24 * dp
    readonly property real s6: 32 * dp

    // ---------- радиусы ----------
    readonly property real rSm: 6 * dp
    readonly property real rMd: 10 * dp
    readonly property real rLg: 14 * dp

    // ---------- длительности, мс ----------
    readonly property int dFast: 150
    readonly property int dBase: 200

    // ---------- шрифты ----------
    readonly property string fSans: "Segoe UI"
    readonly property string fMono: "Cascadia Code"

    // ---------- фоны ----------
    readonly property color bg:     "#090E22"
    readonly property color rail:   "#0C1230"
    readonly property color panel:  "#0F1738"
    readonly property color raised: "#172150"
    readonly property color field:  "#0B1129"

    // ---------- линии ----------
    readonly property color line:   Qt.rgba(0.69, 0.63, 0.90, 0.16)
    readonly property color line2:  Qt.rgba(0.69, 0.63, 0.90, 0.32)

    // ---------- текст (контраст на bg >= 4.5:1, см. contrast.py) ----------
    readonly property color text:   "#EEF0FB"
    readonly property color text2:  "#C5CBE8"
    readonly property color text3:  "#9DA6CC"
    readonly property color text4:  "#8790BA"

    // ---------- акценты ----------
    readonly property color lav:     "#B0A0E6"
    readonly property color lavSoft: Qt.rgba(0.69, 0.63, 0.90, 0.14)
    readonly property color iris:    "#965AD2"
    readonly property color gold:    "#D6AE54"
    readonly property color goldSoft: Qt.rgba(0.84, 0.68, 0.33, 0.16)
    readonly property color accent:     "#C3D9F8"          // серебристый: низ градиента прежней кнопки «Новый разговор»
    readonly property color accentHi:   "#EAF2FF"          // верх градиента
    readonly property color accentSoft: Qt.rgba(0.76, 0.85, 0.97, 0.14)
    readonly property color accentText:   "#050E1C"          // текст на заливке акцента

    // ---------- состояния ----------
    readonly property color ok:   "#79E0BE"
    readonly property color warn: "#EBB95E"
    readonly property color bad:  "#F2909E"
    readonly property color hover: Qt.rgba(0.69, 0.63, 0.90, 0.10)
    readonly property color badSoft: Qt.rgba(0.95, 0.56, 0.62, 0.18)
    readonly property color scrim: Qt.rgba(0.02, 0.03, 0.08, 0.55)
    readonly property color userBorder: Qt.rgba(0.76, 0.85, 0.97, 0.45)
    function veil(a) { return Qt.rgba(0.035, 0.055, 0.133, a) }       // затемнение арта цветом фона
    function lavA(a) { return Qt.rgba(0.69, 0.63, 0.90, a) }

    // ---------- раскладка ----------
    readonly property bool sidebarDocked: false      // история выезжает по кнопке слева
    readonly property bool stageLeft: false         // сцена справа
    function colW(w) { return Math.min(w - 2 * px(20), 720 * fp) }   // ширина колонки чата и композера
}
