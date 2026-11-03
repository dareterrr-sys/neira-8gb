// neira_brain.cpp — реализация бэкенда (Winsock + SSE, сессии).
#include "neira_brain.h"

#include <QMetaObject>
#include <QCoreApplication>
#include <QFile>
#include <QSaveFile>
#include <QTextStream>
#include <QDateTime>
#include <QDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <mutex>
#include <condition_variable>
#include <winsock2.h>
#include <ws2tcpip.h>

#pragma comment(lib, "ws2_32.lib")

static void logLine(const QString &s) {
    QFile f(QStringLiteral("D:/AI/neira-tools/qt_neira/neira_qt.log"));
    if (f.open(QIODevice::Append | QIODevice::WriteOnly)) {
        QTextStream ts(&f);
        ts << QDateTime::currentDateTime().toString(Qt::ISODate) << " " << s << "\n";
    }
}

static QString utf8ToQString(const std::string &s) {
    return QString::fromUtf8(s.data(), (int)s.size());
}

static std::string qStringToUtf8(const QString &s) {
    QByteArray b = s.toUtf8();
    return std::string(b.constData(), b.size());
}

static std::string jsonEscape(const std::string &s) {
    std::string r;
    r.reserve(s.size() + 16);
    for (char c : s) {
        unsigned char uc = (unsigned char)c;
        switch (c) {
            case '\\': r += "\\\\"; break;
            case '"':  r += "\\\""; break;
            case '\n': r += "\\n"; break;
            case '\r': r += "\\r"; break;
            case '\t': r += "\\t"; break;
            default:
                if (uc < 0x20) {
                    char tmp[8];
                    snprintf(tmp, sizeof tmp, "\\u%04x", (unsigned)uc);
                    r += tmp;
                } else {
                    r += c;
                }
        }
    }
    return r;
}

static std::string jsonExtractString(const std::string &j, const std::string &key) {
    std::string needle = "\"" + key + "\"";
    size_t p = j.find(needle);
    if (p == std::string::npos) return "";
    p = j.find(':', p + needle.size());
    if (p == std::string::npos) return "";
    p = j.find('"', p);
    if (p == std::string::npos) return "";
    ++p;
    std::string out;
    for (; p < j.size(); ++p) {
        char c = j[p];
        if (c == '\\' && p + 1 < j.size()) {
            char n = j[++p];
            switch (n) {
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case '"':  out += '"'; break;
                case '\\': out += '\\'; break;
                default: out += n;
            }
        } else if (c == '"') {
            break;
        } else {
            out += c;
        }
    }
    return out;
}

// Строгое извлечение целого числа по JSON-ключу (например, "completion_tokens"
// из usage или "predicted_n" из timings). Возвращает -1, если ключ/число
// не найдены — тогда оценка идёт по символам (/4.0).
static long jsonExtractLong(const std::string &j, const std::string &key) {
    std::string needle = "\"" + key + "\"";
    size_t p = j.find(needle);
    if (p == std::string::npos) return -1;
    p = j.find(':', p + needle.size());
    if (p == std::string::npos) return -1;
    ++p;
    while (p < j.size() && (j[p] == ' ' || j[p] == '\t')) ++p;
    bool neg = false;
    if (p < j.size() && j[p] == '-') { neg = true; ++p; }
    long v = 0;
    bool any = false;
    while (p < j.size() && j[p] >= '0' && j[p] <= '9') {
        v = v * 10 + (j[p] - '0');
        any = true;
        ++p;
    }
    if (!any) return -1;
    return neg ? -v : v;
}

// Итоговое число токенов ответа: точное из метаданных последнего чанка,
// либо оценка (символы / 4.0), округлённая до целого.
static int responseTokensOf(const std::string &lastPayload, double tokensSoFar) {
    long meta = jsonExtractLong(lastPayload, "completion_tokens");
    if (meta < 0) meta = jsonExtractLong(lastPayload, "predicted_n");
    return meta >= 0 ? (int)meta : (int)std::lround(tokensSoFar);
}

// Зачистка незавершённого хвоста генерации (пользователь нажал «Стоп»):
// - обрезаем неполное слово/незакрытую конструкцию в конце;
// - убираем мусорные контрольные символы и U+FFFD (replacement char);
// - возвращаем true, если после чистки не осталось ничего осмысленного —
//   такое сообщение нужно полностью удалить из контекста (защита от Token Loop).
static bool sanitizeInterrupted(QString &s, bool aggressive = false) {
    // 1. хвост — до последней границы (пробел/перенос/разделитель markdown)
    int n = s.size();
    while (n > 0) {
        QChar c = s.at(n - 1);
        if (c.isSpace() || c == QLatin1Char('\n')
            || c == QLatin1Char('`') || c == QLatin1Char('|')) break;
        --n;
    }
    if (n != s.size()) s.truncate(n);

    // 2. мусор: управляющие символы (кроме \n\t\r) и U+FFFD
    QString cleaned;
    cleaned.reserve(s.size());
    for (QChar ch : s) {
        ushort u = ch.unicode();
        if (u == 0xFFFD || (u < 0x20 && u != '\n' && u != '\t' && u != '\r')) continue;
        cleaned += ch;
    }
    s = cleaned;

    // 3. пусто / только пунктуация и маркеры — удалять целиком
    QString t = s.trimmed();
    if (t.isEmpty()) return true;

    // 4. агрессивный режим (только ручной «Стоп»): совсем короткий огрызок
    //    без завершающей пунктуации — это скорее всего незаконченное слово,
    //    удаляем целиком, чтобы не засорять контекст (Token Loop)
    if (aggressive && t.size() <= 12) {
        bool terminated = false;
        for (QChar ch : t) {
            if (ch == QLatin1Char('.') || ch == QLatin1Char('!')
                || ch == QLatin1Char('?') || ch == QLatin1Char('…')) {
                terminated = true;
                break;
            }
        }
        if (!terminated) return true;
    }

    for (QChar ch : t) {
        if (ch.isLetterOrNumber()) return false;
    }
    return true;
}

NeiraBrain::NeiraBrain(QObject *parent) : QObject(parent) {
    m_history.append({QStringLiteral("system"), systemPrompt()});
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);

    // фоновый пингер/восстановитель связи (Exponential Backoff)
    m_reconnectWanted.store(true);
    m_reconnectThread = std::thread([this]() { reconnectLoop(); });
}

NeiraBrain::~NeiraBrain() {
    if (m_thread.joinable()) m_thread.join();
    m_stopReconnect.store(true);
    m_cv.notify_all();
    if (m_reconnectThread.joinable()) m_reconnectThread.join();
    WSACleanup();
}

QString NeiraBrain::systemPrompt() const {
    if (m_codeMode) {
        return QStringLiteral("Ты — инженер-исполнитель. Пишешь только код на C или C++ "
                              "(не Python, не другие языки): без вступлений, без эмоций, "
                              "без пояснений, без дублирования задания.");
    }
    return QStringLiteral("Ты — Нейра, ИИ-девушка, которая живёт в компьютере собеседника. "
                          "Отвечаешь по-русски, живо, но по делу.");
}

void NeiraBrain::setTemperature(double t) {
    if (t < 0.0) t = 0.0;
    if (t > 2.0) t = 2.0;
    if (m_temperature == t) return;
    m_temperature = t;
    emit temperatureChanged();
}

void NeiraBrain::setMaxTokens(int n) {
    if (n < 128) n = 128;
    if (n > 32768) n = 32768;
    if (m_maxTokens == n) return;
    m_maxTokens = n;
    emit maxTokensChanged();
}

void NeiraBrain::setCodeMode(bool on) {
    if (m_codeMode == on) return;
    m_codeMode = on;
    m_history.clear();
    m_history.append({QStringLiteral("system"), systemPrompt()});
    emit codeModeChanged();
}

void NeiraBrain::clearHistory() {
    m_history.clear();
    m_history.append({QStringLiteral("system"), systemPrompt()});
    m_totalTokensSpent = 0;          // новый разговор — счётчик начинается с нуля
    emit totalTokensSpentChanged();
    emit systemMessage(QStringLiteral("— история сброшена —"));
}

// ---------- сессии (сохранение/загрузка) ----------

static QString sessionsDir() {
    return QStringLiteral("D:/AI/neira-tools/sessions/");
}

static QString sanitizeName(const QString &raw) {
    QString name = raw.trimmed();
    if (name.isEmpty()) name = QStringLiteral("сессия");
    QString out;
    for (QChar c : name) {
        if (c.isLetterOrNumber() || c == QLatin1Char('-') || c == QLatin1Char('_')
            || c == QLatin1Char(' ')) {
            out += c;
        } else {
            out += QLatin1Char('_');
        }
    }
    return out;
}

void NeiraBrain::saveSession(const QString &rawName) {
    if (m_busy.load()) {
        emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)"));
        return;
    }
    QString name = sanitizeName(rawName);
    QDir().mkpath(sessionsDir());

    QJsonArray arr;
    for (const auto &m : m_history) {
        if (m.first == QLatin1String("system")) continue;
        QJsonObject o;
        o.insert(QStringLiteral("role"), m.first);
        o.insert(QStringLiteral("content"), m.second);
        arr.append(o);
    }

    QSaveFile f(sessionsDir() + name + QStringLiteral(".json"));
    if (!f.open(QIODevice::WriteOnly)) {
        emit systemMessage(QStringLiteral("(не удалось сохранить сессию)"));
        return;
    }
    f.write(QJsonDocument(arr).toJson(QJsonDocument::Indented));
    f.commit();

    emit systemMessage(QStringLiteral("— сессия «%1» сохранена —").arg(name));
}

void NeiraBrain::loadSession(const QString &rawName) {
    if (m_busy.load()) {
        emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)"));
        return;
    }
    QString name = sanitizeName(rawName);
    QFile f(sessionsDir() + name + QStringLiteral(".json"));
    if (!f.open(QIODevice::ReadOnly)) {
        emit systemMessage(QStringLiteral("(сессия «%1» не найдена)").arg(name));
        return;
    }
    QJsonParseError err{};
    QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isArray()) {
        emit systemMessage(QStringLiteral("(файл сессии повреждён)"));
        return;
    }

    QStringList roles, texts;
    QJsonArray arr = doc.array();
    for (const QJsonValue &v : arr) {
        QJsonObject o = v.toObject();
        QString role = o.value(QStringLiteral("role")).toString();
        QString content = o.value(QStringLiteral("content")).toString();
        if (role.isEmpty()) continue;
        roles << role;
        texts << content;
    }

    m_history.clear();
    m_history.append({QStringLiteral("system"), systemPrompt()});
    for (int i = 0; i < roles.size(); ++i) {
        m_history.append({roles.at(i), texts.at(i)});
    }
    emit historyLoaded(roles, texts);
    emit systemMessage(QStringLiteral("— сессия «%1» загружена —").arg(name));
}

QStringList NeiraBrain::sessionList() const {
    QDir dir(sessionsDir());
    QFileInfoList files = dir.entryInfoList(QStringList() << QStringLiteral("*.json"),
                                            QDir::Files, QDir::Time | QDir::Reversed);
    QStringList out;
    for (const QFileInfo &fi : files) out << fi.completeBaseName();
    return out;
}

void NeiraBrain::stop() {
    logLine(QStringLiteral("stop(): вызван, busy=%1").arg(m_busy.load()));
    if (!m_busy.load()) return;
    m_cancel.store(true);
    std::uintptr_t s = m_socket.exchange(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
    if (s != static_cast<std::uintptr_t>(~std::uintptr_t(0))) {
        shutdown((SOCKET)s, SD_BOTH);
    }
}

// ============================================================
// Авто-переподключение (Exponential Backoff)
// ============================================================

static bool tryTcpConnect() {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return false;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)8080);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    // неблокирующий connect с таймаутом ~1.5 c
    u_long mode = 1;
    ioctlsocket(s, FIONBIO, &mode);

    bool ok = false;
    if (::connect(s, (sockaddr *)&addr, sizeof addr) == 0) {
        ok = true;
    } else {
        fd_set wset;
        FD_ZERO(&wset);
        FD_SET(s, &wset);
        timeval tv{1, 500000};
        if (select(0, nullptr, &wset, nullptr, &tv) > 0) {
            int soerr = 0;
            int len = (int)sizeof(soerr);
            getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&soerr, &len);
            ok = (soerr == 0);
        }
    }
    closesocket(s);
    return ok;
}

// задержки: 1, 2, 4, 8, 16, 30 (потолок), 30, ...
static long backoffDelay(int attempt) {
    if (attempt <= 1) return 1000;
    qint64 back = (qint64)1000 << qMin(attempt - 1, 5);
    return (long)qMin<qint64>(back, 30000);
}

void NeiraBrain::setConnectionStatus(const QString &s) {
    if (m_connectionStatus == s) return;
    m_connectionStatus = s;
    logLine(QStringLiteral("connStatus: ") + s);
    emit connectionStatusChanged();
}

void NeiraBrain::requestReconnect() {
    m_reconnectWanted.store(true);
    m_cv.notify_all();
}

void NeiraBrain::reconnectLoop() {
    const auto idleInterval = std::chrono::seconds(5);

    while (!m_stopReconnect.load()) {
        // --- дежурный режим: связь есть, раз в 5 секунд проверяем её ---
        if (!m_reconnectWanted.load()) {
            if (tryTcpConnect()) {
                std::unique_lock<std::mutex> lk(m_cvMutex);
                m_cv.wait_for(lk, idleInterval, [this]() {
                    return m_stopReconnect.load() || m_reconnectWanted.load();
                });
            } else {
                requestReconnect();   // связь потеряна — переходим к восстановлению
            }
            continue;
        }

        // --- активный режим восстановления с экспоненциальным backoff ---
        int attempt = 0;
        bool failedReported = false;
        while (!m_stopReconnect.load() && m_reconnectWanted.load()) {
            ++attempt;

            if (attempt >= 5 && !failedReported) {
                failedReported = true;
                QMetaObject::invokeMethod(this, [this, attempt]() {
                    m_reconnectAttempt = attempt;
                    emit reconnectAttemptChanged();
                    setConnectionStatus(QStringLiteral("failed"));
                }, Qt::QueuedConnection);
            } else {
                QMetaObject::invokeMethod(this, [this, attempt]() {
                    m_reconnectAttempt = attempt;
                    emit reconnectAttemptChanged();
                    setConnectionStatus(QStringLiteral("reconnecting"));
                }, Qt::QueuedConnection);
            }

            if (tryTcpConnect()) {
                m_reconnectWanted.store(false);   // синхронно, чтобы цикл сразу вышел
                QMetaObject::invokeMethod(this, [this]() {
                    m_reconnectAttempt = 0;
                    emit reconnectAttemptChanged();
                    setConnectionStatus(QStringLiteral("connected"));
                }, Qt::QueuedConnection);
                break;
            }

            long delay = backoffDelay(attempt);
            std::unique_lock<std::mutex> lk(m_cvMutex);
            m_cv.wait_for(lk, std::chrono::milliseconds(delay), [this]() {
                return m_stopReconnect.load() || !m_reconnectWanted.load();
            });
        }
    }
}

void NeiraBrain::appendUser(const QString &text) {
    m_history.append({QStringLiteral("user"), text});
}

QString NeiraBrain::buildPayload(bool stream) const {
    QString out = QStringLiteral("{\"model\":\"brain\",\"messages\":[");
    for (int i = 0; i < m_history.size(); ++i) {
        if (i) out += QLatin1Char(',');
        out += QStringLiteral("{\"role\":\"") + m_history[i].first
             + QStringLiteral("\",\"content\":\"")
             + QString::fromUtf8(jsonEscape(qStringToUtf8(m_history[i].second)).c_str())
             + QStringLiteral("\"}");
    }
    out += QStringLiteral("],\"temperature\":") + QString::number(m_temperature)
         + QStringLiteral(",\"max_tokens\":") + QString::number(m_maxTokens)
         + QStringLiteral(",\"stream\":") + (stream ? QStringLiteral("true") : QStringLiteral("false"))
         + QStringLiteral("}");
    return out;
}

void NeiraBrain::setIsGenerating(bool on) {
    if (m_isGenerating == on) return;
    m_isGenerating = on;
    emit isGeneratingChanged();
}

void NeiraBrain::sendMessage(const QString &text) {
    logLine(QStringLiteral("sendMessage: '") + text.left(40) + QStringLiteral("'"));
    if (m_busy.load()) {
        emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)"));
        return;
    }

    // команды
    if (text.startsWith(QLatin1Char('/'))) {
        if (text == QLatin1String("/new")) { clearHistory(); return; }
        if (text == QLatin1String("/code") || text == QLatin1String("/code on")) {
            setCodeMode(true); emit systemMessage(QStringLiteral("— режим кода включён —")); return;
        }
        if (text == QLatin1String("/code off")) {
            setCodeMode(false); emit systemMessage(QStringLiteral("— режим кода выключен —")); return;
        }
        if (text == QLatin1String("/ctx")) {
            emit systemMessage(QStringLiteral("— история: %1 сообщ.; температура: %2; лимит: %3; режим кода: %4")
                .arg(m_history.size()).arg(m_temperature).arg(m_maxTokens)
                .arg(m_codeMode ? QStringLiteral("вкл") : QStringLiteral("выкл")));
            return;
        }
        if (text.startsWith(QLatin1String("/temp "))) {
            bool ok = false;
            double t = text.mid(6).toDouble(&ok);
            if (ok) setTemperature(t);
            emit systemMessage(QStringLiteral("— температура: %1 —").arg(m_temperature));
            return;
        }
        if (text.startsWith(QLatin1String("/cap "))) {
            bool ok = false;
            int n = text.mid(5).toInt(&ok);
            if (ok) setMaxTokens(n);
            emit systemMessage(QStringLiteral("— лимит: %1 —").arg(m_maxTokens));
            return;
        }
    }

    appendUser(text);
    m_cancel.store(false);
    m_busy.store(true);
    setIsGenerating(true);
    m_status = QStringLiteral("Печатает…");
    emit statusChanged();
    m_speed = QStringLiteral("~0 t/s");   // сброс дисплея скорости перед стартом
    emit speedChanged();

    QString body = buildPayload(true);
    if (m_thread.joinable()) m_thread.join();   // завершить предыдущий (уже закончившийся) поток
    m_thread = std::thread([this, body]() { worker(qStringToUtf8(body)); });
}

void NeiraBrain::worker(const std::string &body) {
    logLine(QStringLiteral("worker: start"));
    // Новая генерация: сбрасываем замер скорости. Без этого isFirstBatch
    // остался бы true с предыдущего ответа, и T0 «повис» бы на прошлой
    // генерации — скорость второй и последующих генераций была бы мусорной.
    isFirstBatch = false;
    generationStartTime = std::chrono::high_resolution_clock::time_point{};
    const char *host = "127.0.0.1";
    const int port = 8080;

    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) {
        logLine(QStringLiteral("worker: socket failed"));
        QMetaObject::invokeMethod(this, [this]() {
            m_busy.store(false);
            setIsGenerating(false);
            m_status = QStringLiteral("Готов"); emit statusChanged();
            emit systemMessage(QStringLiteral("(не удалось создать сокет)"));
        }, Qt::QueuedConnection);
        return;
    }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    inet_pton(AF_INET, host, &addr.sin_addr);

    if (::connect(s, (sockaddr *)&addr, sizeof addr) != 0) {
        logLine(QStringLiteral("worker: connect failed"));
        closesocket(s);
        requestReconnect();
        QMetaObject::invokeMethod(this, [this]() {
            m_busy.store(false);
            setIsGenerating(false);
            m_status = QStringLiteral("Готов"); emit statusChanged();
            emit systemMessage(QStringLiteral("(мозг не ответил — соединение не установлено)"));
        }, Qt::QueuedConnection);
        return;
    }
    logLine(QStringLiteral("worker: connected"));
    m_socket.store((std::uintptr_t)s);

    {
        std::string req = "POST /v1/chat/completions HTTP/1.1\r\n"
                          "Host: 127.0.0.1:8080\r\n"
                          "Content-Type: application/json\r\n"
                          "Content-Length: " + std::to_string(body.size()) + "\r\n"
                          "Connection: close\r\n\r\n" + body;
        size_t sent = 0;
        while (sent < req.size()) {
            int n = send(s, req.data() + sent, (int)(req.size() - sent), 0);
            if (n <= 0) break;
            sent += (size_t)n;
        }
    }

    std::string raw;
    char buf[32768];
    int got;
    bool inHeaders = true;
    bool ok = false;
    QString fullAnswer;
    bool firstDelta = true;
    double tokensSoFar = 0.0;   // накопленные токены текущего ответа (точные или оценка)
    std::string lastPayload;    // последняя data:-строка — для usage/timings-метаданных

    // Таймаут чтения: гарантирует выход из блокирующего recv при «Стоп»
    // (без него поток мог висеть вечно, не доходя до зачистки хвоста).
    DWORD rcvTimeoutMs = 500;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO,
               (const char *)&rcvTimeoutMs, sizeof rcvTimeoutMs);

    // Пакетная отправка токенов в UI: копим дельты и отдаём пачками,
    // чтобы при ~500 т/с не плодить тысячи событий очереди в секунду.
    std::string pendingDeltas;
    DWORD lastBatchFlush = GetTickCount();
    constexpr size_t kBatchChars = 384;      // типичная порция символов
    constexpr DWORD kBatchMs = 24;           // максимум задержки партии

    while (true) {
        got = recv(s, buf, sizeof buf, 0);
        if (got <= 0) {
            int werr = WSAGetLastError();
            if (m_cancel.load()) break;                  // «Стоп» — выходим сразу
            if (werr == WSAETIMEDOUT || werr == WSAEWOULDBLOCK) continue; // тишина
            break;                                       // закрытие потока / ошибка
        }
        if (m_cancel.load()) break;   // пользователь нажал «Стоп»
        raw.append(buf, (size_t)got);
        if (inHeaders) {
            size_t h = raw.find("\r\n\r\n");
            if (h != std::string::npos) {
                std::string headers = raw.substr(0, h + 4);
                raw.erase(0, h + 4);
                inHeaders = false;
                size_t sp1 = headers.find(' ');
                size_t sp2 = sp1 == std::string::npos ? std::string::npos : headers.find(' ', sp1 + 1);
                int status = 0;
                if (sp1 != std::string::npos && sp2 != std::string::npos) {
                    status = atoi(headers.substr(sp1 + 1, sp2 - sp1 - 1).c_str());
                }
                ok = status >= 200 && status < 300;
                if (!ok) {
                    logLine(QStringLiteral("worker: HTTP %1").arg(status));
                    QString err = QStringLiteral("(мозг не ответил — код %1)").arg(status);
                    closesocket(s);
                    m_socket.store(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
                    requestReconnect();
                    QMetaObject::invokeMethod(this, [this, err]() {
                        emit systemMessage(err);
                        m_busy.store(false);
                        setIsGenerating(false);
                        m_status = QStringLiteral("Готов"); emit statusChanged();
                    }, Qt::QueuedConnection);
                    return;
                }
            }
        }
        if (!inHeaders && ok) {
            size_t start = 0;
            while (true) {
                size_t nl = raw.find('\n', start);
                if (nl == std::string::npos) break;
                std::string line = raw.substr(start, nl - start);
                start = nl + 1;
                if (line.rfind("data:", 0) == 0) {
                    std::string payload = line.substr(5);
                    while (!payload.empty() && (payload.back() == '\r' || payload.back() == ' ')) payload.pop_back();
                    if (payload.find("[DONE]") != std::string::npos) {
                        // отдать недосланный хвост перед финальным сигналом
                        if (!pendingDeltas.empty()) {
                            QString tail = utf8ToQString(pendingDeltas);
                            pendingDeltas.clear();
                            QMetaObject::invokeMethod(this, [this, tail]() {
                                emit tokenReceived(tail);
                            }, Qt::QueuedConnection);
                        }
                        int spentTokens = responseTokensOf(lastPayload, tokensSoFar);
                        logLine(QStringLiteral("worker: DONE-prepare raw=%1 canc=%2")
                                    .arg(fullAnswer.size()).arg(m_cancel.load()));
                        closesocket(s);
                        m_socket.store(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
                        logLine(QStringLiteral("worker: done, chars=%1, tokens=%2")
                                    .arg(fullAnswer.size()).arg(spentTokens));
                        QMetaObject::invokeMethod(this, [this, fullAnswer, spentTokens]() {
                            QString clean = fullAnswer;
                            bool junk = sanitizeInterrupted(clean);
                            logLine(QStringLiteral("worker: DONE raw=%1 cleaned=%2 junk=%3")
                                        .arg(fullAnswer.size()).arg(clean.size()).arg(junk));
                            if (!junk) {
                                m_history.append({QStringLiteral("assistant"), clean});
                                emit responseFinished(clean);
                            }
                            m_totalTokensSpent += spentTokens;
                            emit totalTokensSpentChanged();
                            m_busy.store(false);
                            setIsGenerating(false);
                            m_status = QStringLiteral("Готов"); emit statusChanged();
                        }, Qt::QueuedConnection);
                        return;
                    }
                    std::string delta = jsonExtractString(payload, "content");

                    // точное число токенов из метаданных чанка (usage/timings):
                    // есть — берём его, нет — оцениваем по символам (/4.0)
                    long metaTokens = jsonExtractLong(payload, "completion_tokens");
                    if (metaTokens < 0) metaTokens = jsonExtractLong(payload, "predicted_n");
                    if (metaTokens >= 0) {
                        tokensSoFar = (double)metaTokens;
                    } else if (!delta.empty()) {
                        tokensSoFar += (double)delta.size() / 4.0;
                    }
                    lastPayload = payload;

                    if (!delta.empty()) {
                        if (firstDelta) {
                            firstDelta = false;
                            logLine(QStringLiteral("worker: первый токен"));
                            if (delta == "created" || delta.rfind("created", 0) == 0) {
                                continue;
                            }
                        }
                        fullAnswer += utf8ToQString(delta);

                        // --- честный замер скорости: первый батч фиксирует T0,
                        //     каждый следующий батч считает t/s по накопленным
                        //     токенам ответа от T0 ---
                        if (!isFirstBatch) {
                            isFirstBatch = true;
                            generationStartTime = std::chrono::high_resolution_clock::now();
                        } else {
                            auto now = std::chrono::high_resolution_clock::now();
                            double elapsedSeconds =
                                std::chrono::duration<double>(now - generationStartTime).count();
                            if (elapsedSeconds > 0.05) {
                                double tps = tokensSoFar / elapsedSeconds;
                                QString sp = QStringLiteral("%1 t/s").arg(tps, 0, 'f', 1);
                                QMetaObject::invokeMethod(this, [this, sp]() {
                                    m_speed = sp; emit speedChanged();
                                }, Qt::QueuedConnection);
                            }
                        }
                        pendingDeltas += delta;
                        DWORD now2 = GetTickCount();
                        if (pendingDeltas.size() >= kBatchChars || now2 - lastBatchFlush >= kBatchMs) {
                            QString d = utf8ToQString(pendingDeltas);
                            pendingDeltas.clear();
                            lastBatchFlush = now2;
                            QMetaObject::invokeMethod(this, [this, d]() {
                                emit tokenReceived(d);
                            }, Qt::QueuedConnection);
                        }
                    }
                }
            }
            raw.erase(0, start);
        }
    }
    if (!pendingDeltas.empty()) {
        QString tail = utf8ToQString(pendingDeltas);
        pendingDeltas.clear();
        QMetaObject::invokeMethod(this, [this, tail]() {
            emit tokenReceived(tail);
        }, Qt::QueuedConnection);
    }
    int spentTokens = responseTokensOf(lastPayload, tokensSoFar);
    logLine(QStringLiteral("worker: FALLBACK-prepare raw=%1 canc=%2")
                .arg(fullAnswer.size()).arg(m_cancel.load()));
    closesocket(s);
    m_socket.store(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
    bool cancelled = m_cancel.load();
    if (!cancelled) requestReconnect();   // обрыв до [DONE] — запускаем восстановление
    QMetaObject::invokeMethod(this, [this, fullAnswer, cancelled, spentTokens]() {
        if (cancelled) {
            // --- зачистка незавершённого хвоста (Context Cleanup) ---
            QString partial = fullAnswer;
            bool junk = sanitizeInterrupted(partial, true);   // агрессивно: ручной «Стоп»
            if (!junk) {
                // осмысленный текст остался — сохраняем очищенный вариант
                m_history.append({QStringLiteral("assistant"), partial});
                emit responseFinished(partial);
            }
            // системный статус: фиксируем прерывание (QML рисует [SYS_LOG] пилюлю)
            emit systemMessage(junk && !fullAnswer.isEmpty()
                ? QStringLiteral("(генерация остановлена — хвост очищен)")
                : QStringLiteral("(генерация остановлена)"));
        } else if (!fullAnswer.isEmpty()) {
            QString clean = fullAnswer;
            bool junk = sanitizeInterrupted(clean);
            logLine(QStringLiteral("worker: fallback raw=%1 cleaned=%2 junk=%3 canc=%4")
                        .arg(fullAnswer.size()).arg(clean.size()).arg(junk).arg(cancelled));
            if (!junk) {
                m_history.append({QStringLiteral("assistant"), clean});
                emit responseFinished(clean);
            }
        }
        m_totalTokensSpent += spentTokens;
        emit totalTokensSpentChanged();
        m_busy.store(false);
        setIsGenerating(false);
        m_status = QStringLiteral("Готов"); emit statusChanged();
    }, Qt::QueuedConnection);
}
