// neira_brain.cpp — реализация бэкенда (Winsock + SSE, сессии).
#include "neira_brain.h"

#include <QMetaObject>
#include <QCoreApplication>
#include <QFile>
#include <QSaveFile>
#include <QTextStream>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QBuffer>
#include <QImage>
#include <QScreen>
#include <QPixmap>
#include <QGuiApplication>
#include <QDesktopServices>
#include <QUrl>
#include <QVariantMap>
#include <QRegularExpression>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QTimer>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <mutex>
#include <condition_variable>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <mmsystem.h>
#include <commdlg.h>
#include <vector>
#include <QByteArray>

#pragma comment(lib, "ws2_32.lib")

// каталог exe и корень проекта (…/neira-tools/qt_neira → …/AI); переопределяется NEIRA_AI_ROOT
static QString appDir() { return QCoreApplication::applicationDirPath(); }
static QString aiRoot() {
    QString r = qEnvironmentVariable("NEIRA_AI_ROOT");
    if (!r.isEmpty()) return r;
    return QDir::cleanPath(appDir() + QStringLiteral("/../.."));
}

// лог: neira_qt.log рядом с exe, при > 5 МБ — ротация в neira_qt.log.1
static void rotateLogIfBig(const QString &path) {
    QFileInfo fi(path);
    if (fi.exists() && fi.size() > 5 * 1024 * 1024) {
        QFile::remove(path + QStringLiteral(".1"));
        QFile::rename(path, path + QStringLiteral(".1"));
    }
}

static void logLine(const QString &s) {
    static std::mutex mx;
    std::lock_guard<std::mutex> lk(mx);
    const QString path = appDir() + QStringLiteral("/neira_qt.log");
    rotateLogIfBig(path);
    QFile f(path);
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

// Извлечение вложенной JSON-строки: { "<outerKey>": { ... "<key>": "значение" ... } }.
static std::string jsonNestedString(const std::string &j, const std::string &outerKey,
                                    const std::string &key) {
    size_t o = j.find("\"" + outerKey + "\"");
    if (o == std::string::npos) return "";
    o = j.find(':', o + outerKey.size() + 2);
    if (o == std::string::npos) return "";
    o = j.find("\"" + key + "\"", o);
    if (o == std::string::npos) return "";
    o = j.find(':', o + key.size() + 2);
    if (o == std::string::npos) return "";
    o = j.find('"', o);
    if (o == std::string::npos) return "";
    ++o;
    std::string out;
    for (; o < j.size(); ++o) {
        char c = j[o];
        if (c == '\\' && o + 1 < j.size()) {
            char n = j[++o];
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

// ------------------------- WebSocket (RFC 6455) на Winsock -------------------------

static std::mutex g_sendMx;   // отправка в сокет — из нескольких потоков

static bool sendAll(SOCKET s, const std::string &data) {
    std::lock_guard<std::mutex> lk(g_sendMx);
    size_t sent = 0;
    while (sent < data.size()) {
        int n = send(s, data.data() + sent, (int)(data.size() - sent), 0);
        if (n <= 0) return false;
        sent += (size_t)n;
    }
    return true;
}

// Чтение ровно wanted байт с повторными попытками при таймауте (cancel-safe).
static int recvAll(SOCKET s, char *buf, int wanted, const std::atomic<bool> *cancel,
                   int silenceTimeoutMs = 120000) {
    int got = 0;
    DWORD start = GetTickCount();
    while (got < wanted) {
        int n = recv(s, buf + got, wanted - got, 0);
        if (n > 0) { got += n; start = GetTickCount(); continue; }
        if (n == 0) { logLine(QStringLiteral("recvAll: сервер закрыл соединение")); return -1; }
        if (cancel && cancel->load()) return -1;
        int werr = WSAGetLastError();
        if (werr == WSAETIMEDOUT || werr == WSAEWOULDBLOCK) {
            if (GetTickCount() - start > (DWORD)silenceTimeoutMs) { logLine(QStringLiteral("recvAll: тишина")); return -1; }
            continue;
        }
        logLine(QStringLiteral("recvAll: ошибка сокета %1").arg(werr));
        return -1;
    }
    return got;
}

// HTTP Upgrade-рукопожатие к /client-ws. Возвращает true при 101.
static bool wsHandshake(SOCKET s) {
    std::string nonce(16, '\0');
    for (int i = 0; i < 16; ++i) nonce[i] = (char)(GetTickCount() ^ (i * 7919) ^ rand());
    std::string key = QByteArray(nonce.c_str(), 16).toBase64().toStdString();
    std::string req =
        "GET /client-ws HTTP/1.1\r\n"
        "Host: 127.0.0.1:12393\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: " + key + "\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n";
    if (!sendAll(s, req)) return false;
    std::string resp;
    char c = 0;
    while (resp.find("\r\n\r\n") == std::string::npos) {
        int n = recv(s, &c, 1, 0);
        if (n != 1) return false;
        resp += c;
    }
    return resp.find("101") != std::string::npos;
}

static bool wsSendText(SOCKET s, const std::string &payload) {
    std::string frame;
    frame.push_back((char)0x81);   // FIN + text
    uint64_t len = payload.size();
    if (len < 126) {
        frame.push_back((char)(0x80 | len));
    } else if (len < 65536) {
        frame.push_back((char)(0x80 | 126));
        frame.push_back((char)((len >> 8) & 0xFF));
        frame.push_back((char)(len & 0xFF));
    } else {
        frame.push_back((char)(0x80 | 127));
        for (int i = 7; i >= 0; --i) frame.push_back((char)((len >> (8 * i)) & 0xFF));
    }
    uint32_t mask = (uint32_t)(((GetTickCount() & 0xFFFF) << 16) ^ (rand() & 0xFFFF));
    if (mask == 0) mask = 1;
    frame.push_back((char)((mask >> 24) & 0xFF));
    frame.push_back((char)((mask >> 16) & 0xFF));
    frame.push_back((char)((mask >> 8) & 0xFF));
    frame.push_back((char)(mask & 0xFF));
    for (size_t i = 0; i < len; ++i) {
        frame.push_back((char)(payload[i] ^ ((mask >> ((3 - (i & 3)) * 8)) & 0xFF)));
    }
    return sendAll(s, frame);
}

static bool wsSendPong(SOCKET s, const std::string &payload) {
    std::string frame;
    frame.push_back((char)0x8A);   // FIN + pong
    size_t len = payload.size() < 125 ? payload.size() : 125;
    frame.push_back((char)(0x80 | len));   // masked
    uint32_t mask = (uint32_t)((GetTickCount() & 0xFFFF) ^ rand());
    if (mask == 0) mask = 1;
    frame.push_back((char)((mask >> 24) & 0xFF));
    frame.push_back((char)((mask >> 16) & 0xFF));
    frame.push_back((char)((mask >> 8) & 0xFF));
    frame.push_back((char)(mask & 0xFF));
    for (size_t i = 0; i < len; ++i)
        frame.push_back((char)(payload[i] ^ ((mask >> ((3 - (i & 3)) * 8)) & 0xFF)));
    return sendAll(s, frame);
}

// Короткий HTTP/1.1 POST (JSON) для переключения голоса: надёжнее второго WS.
// Читает весь ответ до закрытия соединения (Connection: close), заголовки
// вырезает. Возвращает true, если тело ответа получено.
static bool httpPostJson(const std::string &host, int port, const std::string &path,
                         const std::string &jsonBody, std::string &outBody) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return false;
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    inet_pton(AF_INET, host.c_str(), &addr.sin_addr);
    if (::connect(s, (sockaddr *)&addr, sizeof addr) != 0) {
        closesocket(s);
        return false;
    }
    DWORD tmo = 5000;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&tmo, sizeof tmo);

    std::string req = "POST " + path + " HTTP/1.1\r\n"
        "Host: " + host + ":" + std::to_string(port) + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(jsonBody.size()) + "\r\n"
        "Connection: close\r\n\r\n" + jsonBody;
    int sent = 0;
    while (sent < (int)req.size()) {
        int n = send(s, req.data() + sent, (int)req.size() - sent, 0);
        if (n <= 0) { closesocket(s); return false; }
        sent += n;
    }

    std::string all;
    char buf[8192];
    for (;;) {
        int n = recv(s, buf, sizeof buf, 0);
        if (n <= 0) break;
        all.append(buf, n);
    }
    closesocket(s);

    if (all.empty()) return false;
    size_t hEnd = all.find("\r\n\r\n");
    if (hEnd != std::string::npos) {
        outBody = all.substr(hEnd + 4);
    } else {
        outBody = all;
    }
    return !outBody.empty();
}

// Чтение одного кадра. Возвращает:
//   1 — сообщение полностью прочитано (outPayload, isBinary);
//   0 — ping/pong (не сообщение, продолжать);
//  -1 — закрытие/ошибка/отмена.
static int wsReadFrame(SOCKET s, std::string &outPayload, bool &isBinary,
                       const std::atomic<bool> *cancel, int silenceTimeoutMs = 120000) {
    unsigned char hdr[2];
    if (recvAll(s, (char *)hdr, 2, cancel, silenceTimeoutMs) != 2) return -1;
    int opcode = hdr[0] & 0x0F;
    bool masked = (hdr[1] & 0x80) != 0;
    uint64_t len = hdr[1] & 0x7F;
    if (len == 126) {
        unsigned char e[2];
        if (recvAll(s, (char *)e, 2, cancel, silenceTimeoutMs) != 2) return -1;
        len = ((uint64_t)e[0] << 8) | e[1];
    } else if (len == 127) {
        unsigned char e[8];
        if (recvAll(s, (char *)e, 8, cancel, silenceTimeoutMs) != 8) return -1;
        len = 0;
        for (int i = 0; i < 8; ++i) len = (len << 8) | e[i];
    }
    unsigned char maskKey[4] = {0, 0, 0, 0};
    if (masked) {
        if (recvAll(s, (char *)maskKey, 4, cancel, silenceTimeoutMs) != 4) return -1;
    }
    if (len > 256u * 1024u * 1024u) { logLine(QStringLiteral("ws: слишком большой кадр")); return -1; }
    if (opcode == 0x8) { logLine(QStringLiteral("ws: кадр close от сервера")); return -1; }
    std::string payload((size_t)len, '\0');
    if (len > 0 && recvAll(s, &payload[0], (int)len, cancel, silenceTimeoutMs) != (int)len) return -1;
    if (masked) {
        for (size_t i = 0; i < (size_t)len; ++i) payload[i] ^= maskKey[i & 3];
    }
    // ping: ответить pong с ТЕМ ЖЕ содержимым (иначе сервер закрывает соединение по keepalive)
    if (opcode == 0x9) { wsSendPong(s, payload); return 0; }
    if (opcode == 0xA) return 0;
    isBinary = (opcode == 0x2);
    outPayload = std::move(payload);
    return 1;
}

// Проигрывание wav (base64-декод уже выполнен) через WinMM waveOut. Блокирующий
// синхронный проигрывание: ждём завершения (WOM_DONE) по событию CALLBACK_EVENT.
static void playWavFromBuffer(const QByteArray &wav, std::atomic<std::uintptr_t> &hwoOut,
                              const std::atomic<bool> &abortA, const std::atomic<bool> &abortB,
                              std::atomic<int> &levelOut) {
    if (wav.size() < 44) return;
    const unsigned char *d = (const unsigned char *)wav.constData();
    size_t pos = 12;   // пропустить RIFF/WAVE
    int channels = 1, sr = 24000, bits = 16;
    size_t dataOff = 0, dataLen = 0;
    while (pos + 8 <= (size_t)wav.size()) {
        char id[4];
        memcpy(id, d + pos, 4);
        uint32_t sz = (uint32_t)d[pos + 4] | ((uint32_t)d[pos + 5] << 8)
                    | ((uint32_t)d[pos + 6] << 16) | ((uint32_t)d[pos + 7] << 24);
        if (memcmp(id, "fmt ", 4) == 0) {
            uint16_t tag = (uint16_t)(d[pos + 8] | (d[pos + 9] << 8));
            if (tag == 1) {   // PCM
                channels = d[pos + 10] | (d[pos + 11] << 8);
                sr = d[pos + 12] | (d[pos + 13] << 8) | (d[pos + 14] << 16) | (d[pos + 15] << 24);
                bits = d[pos + 22] | (d[pos + 23] << 8);
            }
        } else if (memcmp(id, "data", 4) == 0) {
            dataOff = pos + 8;
            dataLen = sz;
            break;
        }
        pos += 8 + sz + (sz & 1);
    }
    if (dataLen == 0) return;
    if (dataOff + dataLen > (size_t)wav.size()) dataLen = (size_t)wav.size() - dataOff;
    if (dataLen == 0) return;
    if (channels <= 0) channels = 1;
    WAVEFORMATEX wfx{};
    wfx.wFormatTag = WAVE_FORMAT_PCM;
    wfx.nChannels = (WORD)channels;
    wfx.nSamplesPerSec = (DWORD)sr;
    wfx.wBitsPerSample = (WORD)bits;
    wfx.nBlockAlign = (WORD)(bits / 8 * channels);
    wfx.nAvgBytesPerSec = sr * wfx.nBlockAlign;
    // огибающая громкости (RMS по окнам 40 мс, первый канал) — для рта аватара
    std::vector<int> env;
    if (bits == 16) {
        const int win = std::max(1, sr * 40 / 1000);
        const int16_t *pcm = (const int16_t *)(d + dataOff);
        const size_t frames = dataLen / (2 * (size_t)channels);
        for (size_t f0 = 0; f0 < frames; f0 += (size_t)win) {
            const size_t f1 = std::min(frames, f0 + (size_t)win);
            double acc = 0;
            for (size_t f = f0; f < f1; ++f) { double v = pcm[f * (size_t)channels] / 32768.0; acc += v * v; }
            double rms = std::sqrt(acc / (double)(f1 - f0));
            env.push_back((int)std::min(1000.0, rms * 3200.0));
        }
    }
    HANDLE evt = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    if (!evt) return;
    HWAVEOUT hwo = nullptr;
    if (waveOutOpen(&hwo, WAVE_MAPPER, &wfx, (DWORD_PTR)evt, 0, CALLBACK_EVENT) != MMSYSERR_NOERROR) {
        CloseHandle(evt);
        return;
    }
    WAVEHDR hdr{};
    hdr.lpData = const_cast<char *>(wav.constData() + (qptrdiff)dataOff);
    hdr.dwBufferLength = (DWORD)dataLen;
    if (waveOutPrepareHeader(hwo, &hdr, sizeof hdr) == MMSYSERR_NOERROR) {
        ResetEvent(evt);
        if (waveOutWrite(hwo, &hdr, sizeof hdr) == MMSYSERR_NOERROR) {
            hwoOut.store((std::uintptr_t)hwo);
            DWORD t0 = GetTickCount();
            while (WaitForSingleObject(evt, 40) == WAIT_TIMEOUT) {
                if (!env.empty()) {
                    size_t i = (size_t)((GetTickCount() - t0) / 40);
                    levelOut.store(i < env.size() ? env[i] : 0);
                }
                if (abortA.load() || abortB.load()) { waveOutReset(hwo); break; }
                if (GetTickCount() - t0 > 120000) { waveOutReset(hwo); break; }
            }
            hwoOut.store(0);
            levelOut.store(0);
        }
        waveOutUnprepareHeader(hwo, &hdr, sizeof hdr);
    }
    waveOutClose(hwo);
    CloseHandle(evt);
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

    // режим: NEIRA_QT_BRAIN=ws (по умолчанию, «живой» 12393) | http (запасной, 8080)
    QString mode = qEnvironmentVariable("NEIRA_QT_BRAIN");
    m_wsMode = mode.trimmed().compare(QLatin1String("http"), Qt::CaseInsensitive) != 0;

    // начальный режим голоса — из conf.yaml (tts_model: none_tts => без голоса)
    {
        QFile f(aiRoot() + QStringLiteral("/Open-LLM-VTuber/conf.yaml"));
        if (f.open(QIODevice::ReadOnly)) {
            while (!f.atEnd()) {
                QByteArray line = f.readLine();
                int idx = line.indexOf("tts_model:");
                if (idx >= 0) {
                    m_voiceEnabled = !line.mid(idx + 10).contains("none_tts");
                    break;
                }
            }
        }
    }

    m_demo = qEnvironmentVariable("NEIRA_QT_DEMO") == QLatin1String("1");

    // опрос уровня звука из потока проигрывателя (GUI-поток, 30 Гц); «говорит» держится 300 мс после паузы
    {
        QTimer *t = new QTimer(this);
        t->setInterval(33);
        connect(t, &QTimer::timeout, this, [this]() {
            const double lv = m_mouthA.load() / 1000.0;
            if (std::fabs(lv - m_mouthLevel) > 0.01 || (lv == 0 && m_mouthLevel != 0)) {
                m_mouthLevel = lv;
                emit mouthLevelChanged();
            }
            const qint64 now = QDateTime::currentMSecsSinceEpoch();
            if (m_speakA.load()) m_speakHoldUntil = now + 300;
            const bool sp = now < m_speakHoldUntil;
            if (sp != m_speaking) { m_speaking = sp; emit speakingChanged(); }
        });
        t->start();
        m_levelTimer = t;
    }

    if (m_wsMode) {
        m_playThread = std::thread([this]() { playerLoop(); });
        m_wsThread = std::thread([this]() { wsLoop(); });
        m_probeThread = std::thread([this]() { probeLoop(); });
    } else {
        // фоновый пингер/восстановитель связи (Exponential Backoff) — только для 8080
        m_reconnectWanted.store(true);
        m_reconnectThread = std::thread([this]() { reconnectLoop(); });
    }
}

NeiraBrain::~NeiraBrain() {
    // сначала отмена всего, потом join — иначе закрытие ждёт конца ответа/озвучки
    m_cancel.store(true);
    m_stopReconnect.store(true);
    m_wsStop.store(true);
    m_micStop.store(true);
    m_playStop.store(true);
    m_playAbort.store(true);
    std::uintptr_t ws = m_wsSock.exchange(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
    if (ws != static_cast<std::uintptr_t>(~std::uintptr_t(0))) shutdown((SOCKET)ws, SD_BOTH);
    std::uintptr_t hs = m_socket.exchange(static_cast<std::uintptr_t>(~std::uintptr_t(0)));
    if (hs != static_cast<std::uintptr_t>(~std::uintptr_t(0))) shutdown((SOCKET)hs, SD_BOTH);
    m_cv.notify_all();
    m_playCv.notify_all();
    if (m_micThread.joinable()) m_micThread.join();
    if (m_playThread.joinable()) m_playThread.join();
    if (m_wsThread.joinable()) m_wsThread.join();
    if (m_probeThread.joinable()) m_probeThread.join();
    if (m_thread.joinable()) m_thread.join();
    if (m_reconnectThread.joinable()) m_reconnectThread.join();
    WSACleanup();
}

QString NeiraBrain::appDirUrl() const {
    return QUrl::fromLocalFile(appDir() + QStringLiteral("/")).toString();
}

QString NeiraBrain::systemPrompt() const {
    if (m_codeMode) {
        return QStringLiteral("Ты — инженер-исполнитель. Пишешь только код на C или C++ "
                              "(не Python, не другие языки): без вступлений, без эмоций, "
                              "без пояснений, без дублирования задания.");
    }
    // общая текстовая персона всех чат-клиентов (03.11), запасная строка — если файла нет
    static const QString persona = [] {
        QFile f(aiRoot() + QStringLiteral("/neira-tools/neira_persona.txt"));
        return f.open(QIODevice::ReadOnly) ? QString::fromUtf8(f.readAll()).trimmed() : QString();
    }();
    if (!persona.isEmpty()) return persona;
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

// ============================================================
// Авто-переподключение (Exponential Backoff)
// ============================================================

static bool tryTcpConnect(int port) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return false;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
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
            if (tryTcpConnect(m_wsMode ? 12393 : 8080)) {
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

            if (tryTcpConnect(m_wsMode ? 12393 : 8080)) {
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
    if (m_emotion != QStringLiteral("01")) { m_emotion = QStringLiteral("01"); emit emotionChanged(); }   // новый ход — спокойное лицо
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
    if (text == QLatin1String("/new")) { newChat(); return; }
    if (!m_wsMode && text.startsWith(QLatin1Char('/'))) {
        // параметры генерации и режим кода действуют только в http-режиме (8080)
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

    m_lastUserText = text;
    if (m_wsMode) {
        beginTurn(text, "text-input");
        return;
    }

    appendUser(text);
    m_cancel.store(false);
    m_busy.store(true);
    setIsGenerating(true);
    m_status = QStringLiteral("Печатает…");
    emit statusChanged();
    m_speed = QStringLiteral("—");
    emit speedChanged();

    QString body = buildPayload(true);
    if (m_thread.joinable()) m_thread.join();   // завершить предыдущий (уже закончившийся) поток
    m_thread = std::thread([this, body]() { worker(qStringToUtf8(body)); });
}

void NeiraBrain::worker(const std::string &body) {
    workerHttp(body);
}

void NeiraBrain::workerHttp(const std::string &body) {
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

// ============================================================
// «Живой» режим: WebSocket client-ws (12393) → приложение Нейры.
// Протокол (образец field_test.ws_turns + план «Свой сервер» §4):
//   create-new-history → text-input → audio ×N → backend-synth-complete
//   → frontend-playback-complete → control conversation-chain-end.
// ============================================================
void NeiraBrain::workerVoiceToggle(const std::string &mode) {
    std::string body;
    bool okHttp = httpPostJson("127.0.0.1", 12393, "/set-voice-mode",
                               "{\"mode\":\"" + mode + "\"}", body);
    logLine(QStringLiteral("toggleVoice http: ok=%1 len=%2 body=%3")
                .arg(okHttp)
                .arg(body.size())
                .arg(QString::fromStdString(body).left(160)));
    QMetaObject::invokeMethod(this, [this, okHttp, body]() {
        m_voiceBusy.store(false);
        if (!okHttp || body.empty()) {
            emit systemMessage(QStringLiteral("(не удалось переключить голос: нет ответа от приложения)"));
            return;
        }
        bool ok = body.find("\"ok\":false") == std::string::npos;
        QString replyMode = utf8ToQString(jsonExtractString(body, "mode"));
        QString err = utf8ToQString(jsonExtractString(body, "error"));
        if (ok && (replyMode == "openai_tts" || replyMode == "none_tts")) {
            m_voiceEnabled = (replyMode == "openai_tts");
            emit voiceEnabledChanged();
            emit systemMessage(m_voiceEnabled
                ? QStringLiteral("— голос включён —")
                : QStringLiteral("— голос выключен —"));
        } else {
            QString e = err.isEmpty() ? QStringLiteral("неизвестная ошибка") : err;
            emit systemMessage(QStringLiteral("(не удалось переключить голос: %1)").arg(e));
        }
    }, Qt::QueuedConnection);
}

// ============================================================
// ЖИВОЙ РЕЖИМ: постоянное ws-соединение с приложением Нейры
// ============================================================

static const std::uintptr_t kNoSock = static_cast<std::uintptr_t>(~std::uintptr_t(0));

bool NeiraBrain::wsSend(const QByteArray &json) {
    std::uintptr_t s = m_wsSock.load();
    if (!m_wsUp.load() || s == kNoSock) return false;
    return wsSendText((SOCKET)s, std::string(json.constData(), (size_t)json.size()));
}

static QByteArray jsonMsg(const QString &type, const QVariantMap &extra = QVariantMap()) {
    QJsonObject o;
    o.insert(QStringLiteral("type"), type);
    for (auto it = extra.constBegin(); it != extra.constEnd(); ++it)
        o.insert(it.key(), QJsonValue::fromVariant(it.value()));
    return QJsonDocument(o).toJson(QJsonDocument::Compact);
}

void NeiraBrain::setServices(bool brain, bool voice) {
    if (m_brainUp == brain && m_voiceUp == voice) return;
    m_brainUp = brain;
    m_voiceUp = voice;
    emit servicesChanged();
}

// проверка мозга (8080) и голоса (8090) — для индикатора
void NeiraBrain::probeLoop() {
    while (!m_wsStop.load()) {
        bool b = tryTcpConnect(8080);
        bool v = tryTcpConnect(8090);
        QMetaObject::invokeMethod(this, [this, b, v]() { setServices(b, v); }, Qt::QueuedConnection);
        for (int i = 0; i < 40 && !m_wsStop.load(); ++i) Sleep(100);
    }
}

void NeiraBrain::wsLoop() {
    int attempt = 0;
    while (!m_wsStop.load()) {
        ++attempt;
        QMetaObject::invokeMethod(this, [this, attempt]() {
            m_reconnectAttempt = attempt;
            emit reconnectAttemptChanged();
            setConnectionStatus(attempt >= 5 ? QStringLiteral("failed") : QStringLiteral("reconnecting"));
        }, Qt::QueuedConnection);

        SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        bool ok = false;
        if (s != INVALID_SOCKET) {
            sockaddr_in addr{};
            addr.sin_family = AF_INET;
            addr.sin_port = htons(12393);
            inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
            ok = (::connect(s, (sockaddr *)&addr, sizeof addr) == 0) && wsHandshake(s);
            if (!ok) closesocket(s);
        }
        if (!ok) {
            long delay = backoffDelay(attempt);
            for (long t = 0; t < delay && !m_wsStop.load(); t += 100) Sleep(100);
            continue;
        }

        DWORD rcvTimeoutMs = 500;
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&rcvTimeoutMs, sizeof rcvTimeoutMs);
        m_wsSock.store((std::uintptr_t)s);
        m_wsUp.store(true);
        m_historyReady.store(false);
        attempt = 0;
        logLine(QStringLiteral("ws: подключено"));
        QMetaObject::invokeMethod(this, [this]() {
            m_reconnectAttempt = 0;
            emit reconnectAttemptChanged();
            setConnectionStatus(QStringLiteral("connected"));
        }, Qt::QueuedConnection);
        wsSend(jsonMsg(QStringLiteral("fetch-history-list")));

        while (!m_wsStop.load()) {
            std::string payload;
            bool bin = false;
            int rr = wsReadFrame(s, payload, bin, &m_wsStop, 0x7ffffff0);
            if (rr < 0) break;
            if (rr == 0 || bin) continue;
            wsHandle(QByteArray(payload.data(), (int)payload.size()));
        }

        m_wsUp.store(false);
        QMetaObject::invokeMethod(this, [this]() {
            if (m_pcAvailable || m_pcEnabled || !m_pcConfirm.isEmpty()) {
                m_pcAvailable = false; m_pcEnabled = false; m_pcConfirm.clear();
                emit pcChanged();
            }
        }, Qt::QueuedConnection);
        std::uintptr_t cur = m_wsSock.exchange(kNoSock);
        if (cur != kNoSock) closesocket((SOCKET)cur);
        logLine(QStringLiteral("ws: соединение закрыто"));
        abortPlayback();
        finishTurn(false, QStringLiteral("связь с приложением потеряна"));
        if (m_voiceBusy.exchange(false)) {
            QMetaObject::invokeMethod(this, [this]() {
                emit systemMessage(QStringLiteral("(не удалось переключить голос: связь потеряна)"));
            }, Qt::QueuedConnection);
        }
        if (!m_wsStop.load()) {
            QMetaObject::invokeMethod(this, [this]() {
                setConnectionStatus(QStringLiteral("reconnecting"));
            }, Qt::QueuedConnection);
            Sleep(500);
        }
    }
}

// сообщение от сервера (поток чтения)
void NeiraBrain::wsHandle(const QByteArray &payload) {
    QJsonParseError perr{};
    QJsonDocument doc = QJsonDocument::fromJson(payload, &perr);
    if (perr.error != QJsonParseError::NoError || !doc.isObject()) return;
    const QJsonObject o = doc.object();
    const QString tp = o.value(QStringLiteral("type")).toString();

    if (tp == QLatin1String("audio")) {
        const QString disp = o.value(QStringLiteral("display_text")).toObject()
                                 .value(QStringLiteral("text")).toString();
        QString flush;
        {
            std::lock_guard<std::mutex> lk(m_turnMx);
            if (!m_turnActive) return;   // после «стоп» хвост сервера игнорируем
            if (!disp.isEmpty()) {
                if (!m_gotFirst) { m_gotFirst = true; m_t0 = std::chrono::steady_clock::now(); }
                QString dq = disp;
                {   // метки эмоций: последняя в предложении задаёт лицо Нейры
                    static const QRegularExpression tagRe(QStringLiteral("\\[([A-Za-z_]{2,20})\\]"));
                    QString lastTag;
                    auto it = tagRe.globalMatch(dq);
                    while (it.hasNext()) lastTag = it.next().captured(1);
                    if (!lastTag.isEmpty())
                        QMetaObject::invokeMethod(this, [this, lastTag]() { setEmotionLabel(lastTag); }, Qt::QueuedConnection);
                }
                dq.remove(QRegularExpression(QStringLiteral("\\[[A-Za-z_]{2,20}\\]\\s*")));   // метки эмоций
                if (dq.isEmpty()) goto skipDelta;
                // сервер режет ответ на предложения без пробела между ними
                if (!m_answer.empty() && m_answer.back() != ' ' && m_answer.back() != 0x0A && !dq.at(0).isSpace())
                    dq.prepend(QLatin1Char(' '));
                {
                std::string d = qStringToUtf8(dq);
                m_answer += d;
                m_pending += d;
                DWORD now = GetTickCount();
                if (m_pending.size() >= 384 || now - m_lastFlush >= 24) {
                    flush = utf8ToQString(m_pending);
                    m_pending.clear();
                    m_lastFlush = now;
                }
                }
                skipDelta:;
            }
        }
        if (!flush.isEmpty())
            QMetaObject::invokeMethod(this, [this, flush]() { emit tokenReceived(flush); }, Qt::QueuedConnection);
        const QString b64 = o.value(QStringLiteral("audio")).toString();
        if (!b64.isEmpty()) {
            QByteArray wav = QByteArray::fromBase64(b64.toLatin1());
            {
                std::lock_guard<std::mutex> lk(m_turnMx);
                m_hadAudio = true;
            }
            std::lock_guard<std::mutex> lk(m_playMx);
            m_playQ.push_back(wav);
            m_playCv.notify_all();
        }
    } else if (tp == QLatin1String("backend-synth-complete")) {
        bool now = false;
        {
            std::lock_guard<std::mutex> lk(m_playMx);
            if (m_playQ.empty() && !m_playing) now = true; else m_synthDone = true;
        }
        if (now) wsSend(jsonMsg(QStringLiteral("frontend-playback-complete")));
    } else if (tp == QLatin1String("neira-stress")) {
        double lv = qBound(0.0, o.value(QStringLiteral("level")).toDouble(), 1.0);
        QMetaObject::invokeMethod(this, [this, lv]() {
            if (!qFuzzyCompare(m_stress + 1.0, lv + 1.0)) { m_stress = lv; emit stressChanged(); }
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("neira-stats")) {
        double ts = o.value(QStringLiteral("tok_s")).toDouble(-1);
        int tk = o.value(QStringLiteral("tokens")).toInt(-1);
        int cx = o.value(QStringLiteral("ctx_tokens")).toInt(-1);
        QMetaObject::invokeMethod(this, [this, ts, tk, cx]() {
            if (ts > 0) m_speed = QStringLiteral("%1 ток/с").arg(ts, 0, 'f', 1);
            if (tk >= 0) m_lastTokens = tk;
            emit speedChanged();
            if (cx >= 0) { m_ctxTokens = cx; emit totalTokensSpentChanged(); }
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("control")) {
        if (o.value(QStringLiteral("text")).toString() == QLatin1String("conversation-chain-end"))
            finishTurn(false);
    } else if (tp == QLatin1String("error")) {
        QString msg = o.value(QStringLiteral("message")).toString();
        logLine(QStringLiteral("ws: error ") + msg);
        finishTurn(false, QStringLiteral("ошибка приложения: ") + msg);
    } else if (tp == QLatin1String("interrupt-signal")) {
        finishTurn(false);
    } else if (tp == QLatin1String("user-input-transcription")) {
        QString t = o.value(QStringLiteral("text")).toString();
        QMetaObject::invokeMethod(this, [this, t]() {
            if (t.trimmed().isEmpty()) emit systemMessage(QStringLiteral("(речь не распознана)"));
            else { m_lastUserText = t; emit userTranscribed(t); }
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("history-list")) {
        QVariantList items;
        for (const QJsonValue &v : o.value(QStringLiteral("histories")).toArray()) {
            QJsonObject h = v.toObject();
            QJsonObject lm = h.value(QStringLiteral("latest_message")).toObject();
            QString content = lm.value(QStringLiteral("content")).toString().simplified();
            content.remove(QRegularExpression(QStringLiteral("\\[[A-Za-z_]{2,20}\\]\\s*")));   // метки эмоций [neutral]
            if (content.size() > 60) content = content.left(58) + QStringLiteral("…");
            QDateTime dt = QDateTime::fromString(h.value(QStringLiteral("timestamp")).toString(), Qt::ISODate);
            QVariantMap m;
            m.insert(QStringLiteral("uid"), h.value(QStringLiteral("uid")).toString());
            m.insert(QStringLiteral("title"), dt.isValid() ? dt.toString(QStringLiteral("dd.MM  HH:mm"))
                                                           : h.value(QStringLiteral("uid")).toString());
            m.insert(QStringLiteral("sub"), content);
            items << m;
        }
        QMetaObject::invokeMethod(this, [this, items]() { emit historyListChanged(items); }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("history-data")) {
        QStringList roles, texts, stamps;
        for (const QJsonValue &v : o.value(QStringLiteral("messages")).toArray()) {
            QJsonObject mo = v.toObject();
            QString r = mo.value(QStringLiteral("role")).toString();
            if (r == QLatin1String("human")) r = QStringLiteral("user");
            else if (r == QLatin1String("ai")) r = QStringLiteral("assistant");
            else continue;   // system/metadata не показываем
            roles << r;
            {
                QString c = mo.value(QStringLiteral("content")).toString();
                c.remove(QRegularExpression(QStringLiteral("\\[[A-Za-z_]{2,20}\\]\\s*")));
                c.replace(QRegularExpression(QStringLiteral("([.!?…])(?=[А-ЯЁA-Z])")), QStringLiteral("\\1 "));
                texts << c; stamps << mo.value(QStringLiteral("timestamp")).toString();
            }
        }
        QMetaObject::invokeMethod(this, [this, roles, texts, stamps]() {
            for (int i = roles.size() - 1; i >= 0; --i)
                if (roles.at(i) == QLatin1String("user")) { m_lastUserText = texts.at(i); break; }
            emit historyLoaded(roles, texts, stamps);
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("new-history-created")) {
        QString uid = o.value(QStringLiteral("history_uid")).toString();
        QMetaObject::invokeMethod(this, [this, uid]() {
            m_activeHistory = uid;
            emit activeHistoryChanged();
        }, Qt::QueuedConnection);
        wsSend(jsonMsg(QStringLiteral("fetch-history-list")));
    } else if (tp == QLatin1String("history-deleted")) {
        QString uid = o.value(QStringLiteral("history_uid")).toString();
        QMetaObject::invokeMethod(this, [this, uid]() {
            emit historyDeleted(uid);
            if (uid == m_activeHistory) {
                m_activeHistory.clear();
                m_historyReady.store(false);
                emit activeHistoryChanged();
            }
        }, Qt::QueuedConnection);
        wsSend(jsonMsg(QStringLiteral("fetch-history-list")));
    } else if (tp == QLatin1String("voice-mode-status")) {
        bool ok = o.value(QStringLiteral("ok")).toBool(false);
        QString mode = o.value(QStringLiteral("mode")).toString();
        QString err = o.value(QStringLiteral("error")).toString();
        m_voiceBusy.store(false);
        QMetaObject::invokeMethod(this, [this, ok, mode, err]() {
            const bool isOn = (mode == QLatin1String("on") || mode == QLatin1String("openai_tts"));
            const bool isOff = (mode == QLatin1String("off") || mode == QLatin1String("none_tts"));
            if (ok && (isOn || isOff)) {
                m_voiceEnabled = isOn;
                emit voiceEnabledChanged();
                emit systemMessage(m_voiceEnabled ? QStringLiteral("— голос включён —")
                                                  : QStringLiteral("— голос выключен —"));
            } else {
                emit systemMessage(QStringLiteral("(не удалось переключить голос: %1)")
                                       .arg(err.isEmpty() ? QStringLiteral("неизвестная ошибка") : err));
            }
        }, Qt::QueuedConnection);
    } else if (tp.startsWith(QLatin1String("pc-control-"))) {
        pcHandle(tp, o);
    }
    // прочее (full-text, set-model-and-conf, group-update, force-new-message, control start-mic) — игнорируем
}

// pc-control-*: status {enabled, reason} | confirm-request {id, action, reason} | action {type, desc}
void NeiraBrain::pcHandle(const QString &tp, const QJsonObject &o) {
    if (tp == QLatin1String("pc-control-status")) {
        const bool en = o.value(QStringLiteral("enabled")).toBool(false);
        const QString why = o.value(QStringLiteral("reason")).toString();
        QMetaObject::invokeMethod(this, [this, en, why]() {
            m_pcAvailable = true;
            m_pcEnabled = en;
            m_pcReason = why;
            if (!en) m_pcConfirm.clear();
            emit pcChanged();
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("pc-control-confirm-request")) {
        QVariantMap m;
        m.insert(QStringLiteral("id"), o.value(QStringLiteral("id")).toVariant().toString());
        m.insert(QStringLiteral("action"), o.value(QStringLiteral("action")).toVariant().toString());
        m.insert(QStringLiteral("reason"), o.value(QStringLiteral("reason")).toString());
        QMetaObject::invokeMethod(this, [this, m]() {
            m_pcAvailable = true;
            m_pcConfirm = m;
            emit pcChanged();
        }, Qt::QueuedConnection);
    } else if (tp == QLatin1String("pc-control-action")) {
        QVariantMap m;
        // ключ «type» занят типом самого сообщения, поэтому вид действия читаем из «kind» / «action_type»
        QString kind = o.value(QStringLiteral("kind")).toString();
        if (kind.isEmpty()) kind = o.value(QStringLiteral("action_type")).toString();
        m.insert(QStringLiteral("type"), kind);
        m.insert(QStringLiteral("desc"), o.value(QStringLiteral("desc")).toString());
        m.insert(QStringLiteral("time"), QDateTime::currentDateTime().toString(QStringLiteral("HH:mm:ss")));
        QMetaObject::invokeMethod(this, [this, m]() {
            m_pcAvailable = true;
            m_pcActions.append(m);
            while (m_pcActions.size() > 8) m_pcActions.removeFirst();
            emit pcChanged();
        }, Qt::QueuedConnection);
    }
}

void NeiraBrain::pcSetEnabled(bool on) {
    if (!m_wsUp.load()) { emit systemMessage(QStringLiteral("(приложение Нейры не на связи)")); return; }
    wsSend(jsonMsg(on ? QStringLiteral("pc-control-enable") : QStringLiteral("pc-control-disable")));
}

void NeiraBrain::pcAnswer(const QString &id, bool ok) {
    QVariantMap ex;
    ex.insert(QStringLiteral("id"), id);
    ex.insert(QStringLiteral("ok"), ok);
    wsSend(jsonMsg(QStringLiteral("pc-control-confirm"), ex));
    m_pcConfirm.clear();
    emit pcChanged();
}

void NeiraBrain::setEmotionLabel(const QString &label) {
    // автор 11.11 (вариант B): 15 лиц Нейры по имени метки + старые метки как синонимы
    static const QHash<QString, QString> map = {
        {QStringLiteral("calm"), QStringLiteral("01")},
        {QStringLiteral("predator"), QStringLiteral("02")},
        {QStringLiteral("interest"), QStringLiteral("03")},
        {QStringLiteral("disdain"), QStringLiteral("04")},
        {QStringLiteral("villain_laugh"), QStringLiteral("05")},
        {QStringLiteral("cold_anger"), QStringLiteral("06")},
        {QStringLiteral("surprise"), QStringLiteral("07")},
        {QStringLiteral("thoughtful"), QStringLiteral("08")},
        {QStringLiteral("smug"), QStringLiteral("09")},
        {QStringLiteral("embarrassed"), QStringLiteral("10")},
        {QStringLiteral("bored"), QStringLiteral("11")},
        {QStringLiteral("wink"), QStringLiteral("12")},
        {QStringLiteral("cute"), QStringLiteral("13")},
        {QStringLiteral("sad"), QStringLiteral("14")},
        {QStringLiteral("fear"), QStringLiteral("15")},
        {QStringLiteral("neutral"), QStringLiteral("01")},
        {QStringLiteral("anger"), QStringLiteral("06")},
        {QStringLiteral("disgust"), QStringLiteral("04")},
        {QStringLiteral("joy"), QStringLiteral("13")},
        {QStringLiteral("smirk"), QStringLiteral("09")},
        {QStringLiteral("sadness"), QStringLiteral("14")},
    };
    const auto it = map.constFind(label.toLower());
    if (it == map.constEnd() || *it == m_emotion) return;
    m_emotion = *it;
    emit emotionChanged();
}

void NeiraBrain::debugInject(const QString &json) {
    if (!m_demo) return;
    wsHandle(json.toUtf8());
}

// начало хода (GUI-поток): состояние + отправка
bool NeiraBrain::beginTurn(const QString &userText, const QByteArray &msgType) {
    if (!m_wsUp.load()) {
        emit systemMessage(QStringLiteral("(приложение Нейры не на связи — подожди переподключения)"));
        return false;
    }
    {
        std::lock_guard<std::mutex> lk(m_turnMx);
        m_turnActive = true;
        m_answer.clear();
        m_pending.clear();
        m_lastFlush = GetTickCount();
        m_hadAudio = false;
        m_gotFirst = false;
    }
    {
        std::lock_guard<std::mutex> lk(m_playMx);
        m_playQ.clear();
        m_synthDone = false;
    }
    m_playAbort.store(false);
    m_cancel.store(false);
    m_busy.store(true);
    setIsGenerating(true);
    m_status = QStringLiteral("Печатает…");
    emit statusChanged();
    m_speed = QStringLiteral("—");
    emit speedChanged();

    if (!m_historyReady.exchange(true))
        wsSend(jsonMsg(QStringLiteral("create-new-history")));

    QJsonObject o;
    o.insert(QStringLiteral("type"), QString::fromLatin1(msgType));
    if (msgType == "text-input") {
        o.insert(QStringLiteral("text"), userText);
        QJsonArray imgs;
        for (int i = 0; i < m_attachData.size(); ++i) {
            QJsonObject im;
            im.insert(QStringLiteral("source"), QStringLiteral("upload"));
            im.insert(QStringLiteral("data"), m_attachData.at(i));
            im.insert(QStringLiteral("mime_type"), m_attachMime.at(i));
            imgs.append(im);
        }
        o.insert(QStringLiteral("images"), imgs);
    }
    bool ok = wsSend(QJsonDocument(o).toJson(QJsonDocument::Compact));
    clearAttachments();
    if (!ok) {
        finishTurn(false, QStringLiteral("не удалось отправить сообщение"));
        return false;
    }
    return true;
}

// конец хода (любой поток)
void NeiraBrain::finishTurn(bool cancelled, const QString &errText) {
    std::string ans;
    bool hadAudio;
    double elapsed = 0;
    {
        std::lock_guard<std::mutex> lk(m_turnMx);
        if (!m_turnActive) return;
        m_turnActive = false;
        ans = m_answer;
        hadAudio = m_hadAudio;
        if (m_gotFirst)
            elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - m_t0).count();
        m_pending.clear();   // остаток уйдёт целиком в responseFinished
    }
    int tokens = (int)std::lround(ans.size() / 4.0);
    QMetaObject::invokeMethod(this, [this, ans, cancelled, errText, hadAudio, elapsed, tokens]() {
        QString text = utf8ToQString(ans);
        bool junk = false;
        // при штатном конце ответ от сервера целый — последнее слово не обрезаем
        if (cancelled) junk = sanitizeInterrupted(text, true);
        else junk = text.trimmed().isEmpty();
        if (!junk && !text.isEmpty()) emit responseFinished(text);
        if (cancelled)
            emit systemMessage(junk && !text.isEmpty()
                ? QStringLiteral("(генерация остановлена — хвост очищен)")
                : QStringLiteral("(генерация остановлена)"));
        if (!errText.isEmpty()) emit systemMessage(QStringLiteral("(%1)").arg(errText));
        // скорость и токены — только настоящие, из сообщения сервера neira-stats (задача 13); оценок «≈» нет
        (void)hadAudio; (void)elapsed; (void)tokens;
        m_busy.store(false);
        setIsGenerating(false);
        m_status = QStringLiteral("Готов");
        emit statusChanged();
        wsSend(jsonMsg(QStringLiteral("fetch-history-list")));
    }, Qt::QueuedConnection);
}

void NeiraBrain::abortPlayback() {
    {
        std::lock_guard<std::mutex> lk(m_playMx);
        m_playQ.clear();
        m_synthDone = false;
        m_playAbort.store(true);
        HWAVEOUT h = (HWAVEOUT)m_hwo.load();
        if (h) waveOutReset(h);
    }
    m_playCv.notify_all();
}

void NeiraBrain::playerLoop() {
    while (!m_playStop.load()) {
        QByteArray wav;
        {
            std::unique_lock<std::mutex> lk(m_playMx);
            m_playCv.wait(lk, [this]() { return m_playStop.load() || !m_playQ.empty(); });
            if (m_playStop.load()) break;
            wav = m_playQ.front();
            m_playQ.pop_front();
            m_playing = true;
        }
        m_speakA.store(true);
        if (!m_playAbort.load()) playWavFromBuffer(wav, m_hwo, m_playAbort, m_playStop, m_mouthA);
        m_speakA.store(false);
        m_mouthA.store(0);
        bool sendDone = false;
        {
            std::lock_guard<std::mutex> lk(m_playMx);
            m_playing = false;
            if (m_playQ.empty() && m_synthDone) { m_synthDone = false; sendDone = true; }
        }
        if (sendDone) wsSend(jsonMsg(QStringLiteral("frontend-playback-complete")));
    }
}

// ---------- действия интерфейса ----------

void NeiraBrain::stop() {
    logLine(QStringLiteral("stop(): вызван, busy=%1").arg(m_busy.load()));
    if (m_recording) m_micStop.store(true);
    if (!m_busy.load()) return;
    if (m_wsMode) {
        std::string heard;
        {
            std::lock_guard<std::mutex> lk(m_turnMx);
            heard = m_answer;
        }
        QVariantMap ex;
        ex.insert(QStringLiteral("text"), utf8ToQString(heard));
        wsSend(jsonMsg(QStringLiteral("interrupt-signal"), ex));
        abortPlayback();
        finishTurn(true);
        return;
    }
    m_cancel.store(true);
    std::uintptr_t s = m_socket.exchange(kNoSock);
    if (s != kNoSock) shutdown((SOCKET)s, SD_BOTH);
}

void NeiraBrain::regenerate() {
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    if (m_lastUserText.isEmpty()) { emit systemMessage(QStringLiteral("(нечего повторять)")); return; }
    QString t = m_lastUserText;
    if (m_wsMode) { beginTurn(t, "text-input"); return; }
    // http: убираем последний ответ из истории и повторяем вопрос
    while (!m_history.isEmpty() && m_history.last().first == QLatin1String("assistant")) m_history.removeLast();
    if (!m_history.isEmpty() && m_history.last().first == QLatin1String("user")) m_history.removeLast();
    sendMessage(t);
}

void NeiraBrain::proactiveSpeak() {
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    if (!m_wsMode) { emit systemMessage(QStringLiteral("(работает только в живом режиме)")); return; }
    beginTurn(QString(), "ai-speak-signal");
}

void NeiraBrain::refreshHistory() {
    if (m_wsMode) wsSend(jsonMsg(QStringLiteral("fetch-history-list")));
}

void NeiraBrain::openHistory(const QString &uid) {
    if (!m_wsMode || uid.isEmpty()) return;
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    QVariantMap ex;
    ex.insert(QStringLiteral("history_uid"), uid);
    if (!wsSend(jsonMsg(QStringLiteral("fetch-and-set-history"), ex))) {
        emit systemMessage(QStringLiteral("(приложение Нейры не на связи)"));
        return;
    }
    m_historyReady.store(true);
    m_activeHistory = uid;
    emit activeHistoryChanged();
    m_totalTokensSpent = 0; m_ctxTokens = -1;
    emit totalTokensSpentChanged();
    m_lastUserText.clear();
}

void NeiraBrain::deleteHistory(const QString &uid) {
    if (!m_wsMode || uid.isEmpty()) return;
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    QVariantMap ex;
    ex.insert(QStringLiteral("history_uid"), uid);
    wsSend(jsonMsg(QStringLiteral("delete-history"), ex));
}

void NeiraBrain::newChat() {
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    m_totalTokensSpent = 0; m_ctxTokens = -1;
    m_lastTokens = 0;
    m_lastUserText.clear();
    clearAttachments();
    emit totalTokensSpentChanged();
    if (m_wsMode) {
        m_historyReady.store(wsSend(jsonMsg(QStringLiteral("create-new-history"))));
        m_activeHistory.clear();
        emit activeHistoryChanged();
    } else {
        m_history.clear();
        m_history.append({QStringLiteral("system"), systemPrompt()});
    }
}

void NeiraBrain::openExternal(const QString &url) {
    QUrl u(url);
    if (u.scheme() == QLatin1String("http") || u.scheme() == QLatin1String("https"))
        QDesktopServices::openUrl(u);
}

// ---------- вложения ----------

static bool encodeImage(const QImage &src, QString &dataUri, QString &mime) {
    if (src.isNull()) return false;
    QImage img = src;
    if (img.width() > 1600 || img.height() > 1600)
        img = img.scaled(1600, 1600, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    QByteArray bytes;
    QBuffer buf(&bytes);
    buf.open(QIODevice::WriteOnly);
    if (img.convertToFormat(QImage::Format_RGB32).save(&buf, "JPEG", 85)) {
        mime = QStringLiteral("image/jpeg");
    } else {
        bytes.clear();
        QBuffer b2(&bytes);
        b2.open(QIODevice::WriteOnly);
        if (!img.save(&b2, "PNG")) return false;
        mime = QStringLiteral("image/png");
    }
    dataUri = QStringLiteral("data:") + mime + QStringLiteral(";base64,") + QString::fromLatin1(bytes.toBase64());
    return true;
}

void NeiraBrain::attachImage() {
    wchar_t file[MAX_PATH] = L"";
    OPENFILENAMEW ofn{};
    ofn.lStructSize = sizeof ofn;
    ofn.hwndOwner = GetActiveWindow();
    ofn.lpstrFilter = L"Картинки\0*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp\0Все файлы\0*.*\0";
    ofn.lpstrFile = file;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetOpenFileNameW(&ofn)) return;
    QString path = QString::fromWCharArray(file);
    QImage img(path);
    QString uri, mime;
    if (!encodeImage(img, uri, mime)) {
        emit systemMessage(QStringLiteral("(не удалось прочитать картинку)"));
        return;
    }
    m_attachNames << QFileInfo(path).fileName();
    m_attachData << uri;
    m_attachMime << mime;
    emit attachmentsChanged();
}

void NeiraBrain::attachScreenshot() {
    QScreen *scr = QGuiApplication::primaryScreen();
    if (!scr) { emit systemMessage(QStringLiteral("(экран недоступен)")); return; }
    QImage img = scr->grabWindow(0).toImage();
    QString uri, mime;
    if (!encodeImage(img, uri, mime)) {
        emit systemMessage(QStringLiteral("(не удалось сделать снимок экрана)"));
        return;
    }
    m_attachNames << QStringLiteral("снимок экрана ") + QDateTime::currentDateTime().toString(QStringLiteral("HH:mm:ss"));
    m_attachData << uri;
    m_attachMime << mime;
    emit attachmentsChanged();
}

void NeiraBrain::removeAttachment(int index) {
    if (index < 0 || index >= m_attachNames.size()) return;
    m_attachNames.removeAt(index);
    m_attachData.removeAt(index);
    m_attachMime.removeAt(index);
    emit attachmentsChanged();
}

void NeiraBrain::clearAttachments() {
    if (m_attachNames.isEmpty()) return;
    m_attachNames.clear();
    m_attachData.clear();
    m_attachMime.clear();
    emit attachmentsChanged();
}

// ---------- микрофон (WinMM waveIn, 16 кГц, моно) ----------

void NeiraBrain::toggleMic() {
    if (m_recording) {
        m_micStop.store(true);   // поток записи сам отправит запись
        return;
    }
    if (!m_wsMode) { emit systemMessage(QStringLiteral("(микрофон работает только в живом режиме)")); return; }
    if (m_busy.load()) { emit systemMessage(QStringLiteral("(подожди — ответ ещё идёт)")); return; }
    if (!m_wsUp.load()) { emit systemMessage(QStringLiteral("(приложение Нейры не на связи)")); return; }
    if (m_micThread.joinable()) m_micThread.join();
    m_micStop.store(false);
    m_recording = true;
    emit recordingChanged();
    m_micThread = std::thread([this]() { micLoop(); });
}

void NeiraBrain::micLoop() {
    constexpr int kRate = 16000;
    constexpr int kBufSamples = 1600;   // 100 мс
    constexpr int kBufs = 4;
    WAVEFORMATEX wfx{};
    wfx.wFormatTag = WAVE_FORMAT_PCM;
    wfx.nChannels = 1;
    wfx.nSamplesPerSec = kRate;
    wfx.wBitsPerSample = 16;
    wfx.nBlockAlign = 2;
    wfx.nAvgBytesPerSec = kRate * 2;

    std::vector<int16_t> pcm;
    HANDLE evt = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    HWAVEIN hwi = nullptr;
    bool opened = evt && waveInOpen(&hwi, WAVE_MAPPER, &wfx, (DWORD_PTR)evt, 0, CALLBACK_EVENT) == MMSYSERR_NOERROR;
    if (!opened) {
        if (evt) CloseHandle(evt);
        QMetaObject::invokeMethod(this, [this]() {
            m_recording = false;
            emit recordingChanged();
            emit systemMessage(QStringLiteral("(микрофон недоступен)"));
        }, Qt::QueuedConnection);
        return;
    }
    std::vector<std::vector<int16_t>> bufs(kBufs, std::vector<int16_t>(kBufSamples));
    WAVEHDR hdr[kBufs]{};
    for (int i = 0; i < kBufs; ++i) {
        hdr[i].lpData = (LPSTR)bufs[i].data();
        hdr[i].dwBufferLength = kBufSamples * 2;
        waveInPrepareHeader(hwi, &hdr[i], sizeof(WAVEHDR));
        waveInAddBuffer(hwi, &hdr[i], sizeof(WAVEHDR));
    }
    waveInStart(hwi);
    DWORD t0 = GetTickCount();
    auto drain = [&]() {
        for (int i = 0; i < kBufs; ++i) {
            if (hdr[i].dwFlags & WHDR_DONE) {
                size_t n = hdr[i].dwBytesRecorded / 2;
                pcm.insert(pcm.end(), bufs[i].begin(), bufs[i].begin() + n);
                hdr[i].dwFlags &= ~WHDR_DONE;
                hdr[i].dwBytesRecorded = 0;
                if (!m_micStop.load()) waveInAddBuffer(hwi, &hdr[i], sizeof(WAVEHDR));
            }
        }
    };
    while (!m_micStop.load() && GetTickCount() - t0 < 60000) {
        WaitForSingleObject(evt, 100);
        drain();
    }
    m_micStop.store(true);
    waveInStop(hwi);
    waveInReset(hwi);
    drain();
    for (int i = 0; i < kBufs; ++i) waveInUnprepareHeader(hwi, &hdr[i], sizeof(WAVEHDR));
    waveInClose(hwi);
    CloseHandle(evt);

    QMetaObject::invokeMethod(this, [this]() { m_recording = false; emit recordingChanged(); }, Qt::QueuedConnection);
    if (m_wsStop.load()) return;

    if (pcm.size() < (size_t)kRate * 3 / 10) {
        QMetaObject::invokeMethod(this, [this]() { emit systemMessage(QStringLiteral("(запись слишком короткая)")); },
                                  Qt::QueuedConnection);
        return;
    }
    // ход начинается здесь: состояние — сразу, GUI-часть — в очереди (раньше любых ответов сервера)
    {
        std::lock_guard<std::mutex> lk(m_turnMx);
        m_turnActive = true;
        m_answer.clear();
        m_pending.clear();
        m_lastFlush = GetTickCount();
        m_hadAudio = false;
        m_gotFirst = false;
    }
    {
        std::lock_guard<std::mutex> lk(m_playMx);
        m_playQ.clear();
        m_synthDone = false;
    }
    m_playAbort.store(false);
    m_busy.store(true);
    QMetaObject::invokeMethod(this, [this]() {
        m_cancel.store(false);
        setIsGenerating(true);
        m_status = QStringLiteral("Слушает…");
        emit statusChanged();
        m_speed = QStringLiteral("—");
        emit speedChanged();
    }, Qt::QueuedConnection);

    if (!m_historyReady.exchange(true)) wsSend(jsonMsg(QStringLiteral("create-new-history")));
    bool ok = true;
    const size_t chunk = 8000;   // 0.5 с на сообщение
    for (size_t pos = 0; pos < pcm.size() && ok; pos += chunk) {
        size_t n = std::min(chunk, pcm.size() - pos);
        QJsonArray arr;
        for (size_t i = 0; i < n; ++i) arr.append(pcm[pos + i] / 32768.0);
        QJsonObject o;
        o.insert(QStringLiteral("type"), QStringLiteral("mic-audio-data"));
        o.insert(QStringLiteral("audio"), arr);
        ok = wsSend(QJsonDocument(o).toJson(QJsonDocument::Compact));
    }
    if (ok) ok = wsSend(jsonMsg(QStringLiteral("mic-audio-end")));
    if (!ok) finishTurn(false, QStringLiteral("не удалось отправить запись"));
}

void NeiraBrain::toggleVoice() {
    if (m_voiceBusy.load()) {
        emit systemMessage(QStringLiteral("(переключение голоса уже идёт…)"));
        return;
    }
    const char *mode = m_voiceEnabled ? "off" : "on";
    logLine(QStringLiteral("toggleVoice -> ") + QString::fromLatin1(mode));
    if (m_wsMode) {
        // через постоянное соединение: сервер заодно обновит движок именно этой сессии
        if (!m_wsUp.load()) {
            emit systemMessage(QStringLiteral("(приложение Нейры не на связи)"));
            return;
        }
        emit systemMessage(m_voiceEnabled
            ? QStringLiteral("(выключаю голос…)")
            : QStringLiteral("(включаю голос… это может занять до 2 минут)"));
        m_voiceBusy.store(true);
        QVariantMap ex;
        ex.insert(QStringLiteral("mode"), QString::fromLatin1(mode));
        if (!wsSend(jsonMsg(QStringLiteral("set-voice-mode"), ex))) m_voiceBusy.store(false);
        return;
    }
    emit systemMessage(m_voiceEnabled
        ? QStringLiteral("(выключаю голос…)")
        : QStringLiteral("(включаю голос… это может занять до 2 минут)"));
    m_voiceBusy.store(true);
    m_cancel.store(false);
    if (m_thread.joinable()) m_thread.join();
    m_thread = std::thread([this, mode]() { workerVoiceToggle(mode); });
}
