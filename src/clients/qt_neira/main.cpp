// main.cpp — точка входа Qt/QML приложения Нейры.
#include <windows.h>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QtQuickControls2/QQuickStyle>
#include <QFile>
#include <QTextStream>
#include <QDateTime>
#include "neira_brain.h"

static void msgToFile(QtMsgType type, const QMessageLogContext &, const QString &msg) {
    QFile f(QStringLiteral("D:/AI/neira-tools/qt_neira/neira_qt.log"));
    if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
        QTextStream ts(&f);
        ts << QDateTime::currentDateTime().toString(Qt::ISODate) << " "
           << msg << "\n";
    }
}

static LONG WINAPI crashHandler(EXCEPTION_POINTERS *) {
    QFile f(QStringLiteral("D:/AI/neira-tools/qt_neira/neira_qt.log"));
    if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
        QTextStream ts(&f);
        ts << QDateTime::currentDateTime().toString(Qt::ISODate)
           << " CRASH: необработанное исключение (SEH)\n";
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

int main(int argc, char *argv[]) {
    qInstallMessageHandler(msgToFile);
    SetUnhandledExceptionFilter(crashHandler);

    QQuickStyle::setStyle(QStringLiteral("Basic"));

    // Честный High-DPI: нативный масштаб без округления (PassThrough),
    // чтобы на 125%/150% системных масштабах не было размытия и сдвигов.
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);

    QGuiApplication app(argc, argv);

    NeiraBrain brain;
    QQmlApplicationEngine engine;

    engine.rootContext()->setContextProperty("brain", &brain);
    engine.load(QUrl(QStringLiteral("file:///D:/AI/neira-tools/qt_neira/qml/Main.qml")));

    if (engine.rootObjects().isEmpty()) {
        QFile f(QStringLiteral("D:/AI/neira-tools/qt_neira/neira_qt.log"));
        if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
            QTextStream ts(&f);
            ts << QDateTime::currentDateTime().toString(Qt::ISODate)
               << " FATAL: нет корневых объектов QML (engine.load не сработал)\n";
        }
        return 1;
    }

    return app.exec();
}
