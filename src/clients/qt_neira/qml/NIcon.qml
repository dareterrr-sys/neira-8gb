// NIcon.qml — одноцветная иконка из icons/svg (тон задаётся tint).
import QtQuick
import QtQuick.Effects

Item {
    id: ico
    property string name: ""
    property color tint: Theme.text3
    property real iconSize: 16

    // implicit-размер, а не width/height: внутри Layout явный размер «застывает»
    implicitWidth: iconSize
    implicitHeight: iconSize

    Image {
        anchors.fill: parent
        source: brain.appDirUrl + "icons/svg/" + ico.name + ".svg"
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
