// main.cpp — точка входа Qt/QML приложения Нейры.
#include <windows.h>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QtQuickControls2/QQuickStyle>
#include <QFile>
#include <QTextStream>
#include <QDateTime>
#include <QCoreApplication>
#include <QFileInfo>
#include <QUrl>
#include <QWindow>
#include <QScreen>
#include <QSettings>
#include <QDebug>
#include <memory>
#include "neira_brain.h"

// лог лежит рядом с exe; при размере > 5 МБ переносится в neira_qt.log.1
static QString logPath() {
    const QString path = QCoreApplication::applicationDirPath() + QStringLiteral("/neira_qt.log");
    QFileInfo fi(path);
    if (fi.exists() && fi.size() > 5 * 1024 * 1024) {
        QFile::remove(path + QStringLiteral(".1"));
        QFile::rename(path, path + QStringLiteral(".1"));
    }
    return path;
}

static void msgToFile(QtMsgType type, const QMessageLogContext &, const QString &msg) {
    QFile f(logPath());
    if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
        QTextStream ts(&f);
        ts << QDateTime::currentDateTime().toString(Qt::ISODate) << " "
           << msg << "\n";
    }
}

static LONG WINAPI crashHandler(EXCEPTION_POINTERS *) {
    QFile f(QCoreApplication::applicationDirPath() + QStringLiteral("/neira_qt.log"));
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
    engine.load(QUrl::fromLocalFile(QCoreApplication::applicationDirPath() + QStringLiteral("/qml/Main.qml")));

    if (engine.rootObjects().isEmpty()) {
        QFile f(QCoreApplication::applicationDirPath() + QStringLiteral("/neira_qt.log"));
        if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
            QTextStream ts(&f);
            ts << QDateTime::currentDateTime().toString(Qt::ISODate)
               << " FATAL: нет корневых объектов QML (engine.load не сработал)\n";
        }
        return 1;
    }

    // Положение и размер окна (приёмка 11.11: окно открывалось развёрнутым на весь монитор). Хранится рядом с exe;
    // сохраняется только обычное (не развёрнутое и не полноэкранное) состояние, запуск — всегда в обычном виде.
    if (auto *win = qobject_cast<QWindow *>(engine.rootObjects().first())) {
        const QString ini = QCoreApplication::applicationDirPath() + QStringLiteral("/neira_window.ini");
        bool sizeArg = false;
        for (const QString &a : QCoreApplication::arguments()) if (a.startsWith(QStringLiteral("--size="))) sizeArg = true;
        if (win->visibility() == QWindow::Maximized || win->visibility() == QWindow::FullScreen) win->showNormal();
        QSettings st(ini, QSettings::IniFormat);
        if (!sizeArg && st.contains(QStringLiteral("rect"))) {
            const QRect r = st.value(QStringLiteral("rect")).toRect();
            bool onScreen = false;   // окно должно хоть наполовину попадать на какой-нибудь из мониторов
            for (QScreen *sc : QGuiApplication::screens())
                if (sc->availableGeometry().intersected(r).width() >= r.width() / 2 &&
                    sc->availableGeometry().intersected(r).height() >= r.height() / 2) onScreen = true;
            if (onScreen && r.width() >= win->minimumWidth() && r.height() >= win->minimumHeight()) win->setGeometry(r);
        }
        // к aboutToQuit окно уже скрыто, поэтому запоминаем последний обычный прямоугольник по ходу работы
        auto last = std::make_shared<QRect>(win->geometry());
        auto track = [win, last]() { if (win->visibility() == QWindow::Windowed) *last = win->geometry(); };
        QObject::connect(win, &QWindow::xChanged, track);
        QObject::connect(win, &QWindow::yChanged, track);
        QObject::connect(win, &QWindow::widthChanged, track);
        QObject::connect(win, &QWindow::heightChanged, track);
        QObject::connect(&app, &QCoreApplication::aboutToQuit, [last, ini, sizeArg]() {
            if (sizeArg) return;   // снимки с --size положение не меняют
            QSettings(ini, QSettings::IniFormat).setValue(QStringLiteral("rect"), *last);
        });
    }

    return app.exec();
}
