// neira_brain.h — бэкенд Нейры для Qt/QML.
// Режим «живой» (по умолчанию): одно постоянное ws-соединение с приложением Нейры (12393, /client-ws).
// Режим http (NEIRA_QT_BRAIN=http): прямой SSE к мозгу на 8080 (запасной).
#ifndef NEIRA_BRAIN_H
#define NEIRA_BRAIN_H

#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>
#include <QJsonObject>
#include <QVector>
#include <QPair>
#include <QByteArray>
#include <string>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <deque>
#include <cstdint>
#include <chrono>

class NeiraBrain : public QObject {
    Q_OBJECT
    // параметры генерации (temperature/maxTokens/codeMode) действуют только в режиме http (8080);
    // в «живом» режиме ими управляют сервер и совет, в интерфейсе их нет
    Q_PROPERTY(double temperature READ temperature WRITE setTemperature NOTIFY temperatureChanged)
    Q_PROPERTY(int maxTokens READ maxTokens WRITE setMaxTokens NOTIFY maxTokensChanged)
    Q_PROPERTY(bool codeMode READ codeMode WRITE setCodeMode NOTIFY codeModeChanged)
    Q_PROPERTY(bool voiceEnabled READ voiceEnabled NOTIFY voiceEnabledChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(int lastTokens READ lastTokens NOTIFY speedChanged)
    Q_PROPERTY(int totalTokensSpent READ totalTokensSpent NOTIFY totalTokensSpentChanged)
    // из сообщений сервера (задача 13): токенов в разговоре (-1 — ещё не пришло) и уровень перегрузки 0..1
    Q_PROPERTY(int ctxTokens READ ctxTokens NOTIFY totalTokensSpentChanged)
    Q_PROPERTY(double stress READ stress NOTIFY stressChanged)
    Q_PROPERTY(bool isGenerating READ isGenerating NOTIFY isGeneratingChanged)
    Q_PROPERTY(QString connectionStatus READ connectionStatus NOTIFY connectionStatusChanged)
    Q_PROPERTY(int reconnectAttempt READ reconnectAttempt NOTIFY reconnectAttemptChanged)
    Q_PROPERTY(bool brainUp READ brainUp NOTIFY servicesChanged)
    Q_PROPERTY(bool voiceUp READ voiceUp NOTIFY servicesChanged)
    Q_PROPERTY(bool recording READ recording NOTIFY recordingChanged)
    Q_PROPERTY(QStringList attachments READ attachments NOTIFY attachmentsChanged)
    Q_PROPERTY(QString activeHistory READ activeHistory NOTIFY activeHistoryChanged)
    Q_PROPERTY(QString appDirUrl READ appDirUrl CONSTANT)
    // громкость проигрываемого звука 0..1 (для рта аватара) и признак «Нейра говорит»
    Q_PROPERTY(double mouthLevel READ mouthLevel NOTIFY mouthLevelChanged)
    Q_PROPERTY(bool speaking READ speaking NOTIFY speakingChanged)
    Q_PROPERTY(QString emotion READ emotion NOTIFY emotionChanged)   // метка эмоции из ответа сервера ([joy] и т. п.) → ключ лица "01".."15"
    // управление ПК (pc-control-*): доступно, когда сервер хоть раз прислал pc-control-*
    Q_PROPERTY(bool pcAvailable READ pcAvailable NOTIFY pcChanged)
    Q_PROPERTY(bool pcEnabled READ pcEnabled NOTIFY pcChanged)
    Q_PROPERTY(QString pcReason READ pcReason NOTIFY pcChanged)
    Q_PROPERTY(QVariantMap pcConfirm READ pcConfirm NOTIFY pcChanged)   // {id, action, reason}; пусто = нет запроса
    Q_PROPERTY(QVariantList pcActions READ pcActions NOTIFY pcChanged)  // [{type, desc, time}], новые в конце
    Q_PROPERTY(bool demoMode READ demoMode CONSTANT)                    // NEIRA_QT_DEMO=1: отладочная подача сообщений

public:
    explicit NeiraBrain(QObject *parent = nullptr);
    ~NeiraBrain();

    double temperature() const { return m_temperature; }
    int maxTokens() const { return m_maxTokens; }
    bool codeMode() const { return m_codeMode; }
    bool voiceEnabled() const { return m_voiceEnabled; }
    QString status() const { return m_status; }
    QString speed() const { return m_speed; }
    int lastTokens() const { return m_lastTokens; }
    int totalTokensSpent() const { return m_totalTokensSpent; }
    int ctxTokens() const { return m_ctxTokens; }
    double stress() const { return m_stress; }
    bool isGenerating() const { return m_isGenerating; }
    QString connectionStatus() const { return m_connectionStatus; }
    int reconnectAttempt() const { return m_reconnectAttempt; }
    bool brainUp() const { return m_brainUp; }
    bool voiceUp() const { return m_voiceUp; }
    bool recording() const { return m_recording; }
    QStringList attachments() const { return m_attachNames; }
    QString activeHistory() const { return m_activeHistory; }
    QString appDirUrl() const;
    double mouthLevel() const { return m_mouthLevel; }
    QString emotion() const { return m_emotion; }
    bool speaking() const { return m_speaking; }
    bool pcAvailable() const { return m_pcAvailable; }
    bool pcEnabled() const { return m_pcEnabled; }
    QString pcReason() const { return m_pcReason; }
    QVariantMap pcConfirm() const { return m_pcConfirm; }
    QVariantList pcActions() const { return m_pcActions; }
    bool demoMode() const { return m_demo; }

    void setTemperature(double t);
    void setMaxTokens(int n);
    void setCodeMode(bool on);

public slots:
    void sendMessage(const QString &text);
    void regenerate();              // повторить последнее сообщение пользователя
    void proactiveSpeak();          // ai-speak-signal: Нейра сама предлагает тему
    void stop();
    void toggleVoice();
    void toggleMic();               // запись с микрофона → mic-audio-data/mic-audio-end
    void attachImage();             // выбрать файл-картинку
    void attachScreenshot();        // снимок экрана
    void removeAttachment(int index);
    void clearAttachments();
    // история — на сервере
    void refreshHistory();
    void openHistory(const QString &uid);
    void deleteHistory(const QString &uid);
    void newChat();
    void clearHistory() { newChat(); }
    void pcSetEnabled(bool on);                      // pc-control-enable / pc-control-disable
    void pcAnswer(const QString &id, bool ok);       // pc-control-confirm {id, ok}
    void debugInject(const QString &json);
    Q_INVOKABLE void setEmotionLabel(const QString &label);   // метка сервера → лицо; неизвестная метка не меняет лицо           // только при NEIRA_QT_DEMO=1: подать сообщение «как от сервера»
    void openExternal(const QString &url);   // ссылки из сообщений (только http/https)

signals:
    void temperatureChanged();
    void maxTokensChanged();
    void codeModeChanged();
    void voiceEnabledChanged();
    void statusChanged();
    void speedChanged();
    void totalTokensSpentChanged();
    void stressChanged();
    void isGeneratingChanged();
    void tokenReceived(const QString &delta);
    void responseFinished(const QString &full);
    void systemMessage(const QString &text);
    void historyLoaded(const QStringList &roles, const QStringList &texts, const QStringList &stamps);   // stamps: ISO-время сообщений
    void historyListChanged(const QVariantList &items);   // {uid, title, sub}
    void historyDeleted(const QString &uid);
    void activeHistoryChanged();
    void userTranscribed(const QString &text);            // распознанная речь пользователя
    void connectionStatusChanged();
    void reconnectAttemptChanged();
    void servicesChanged();
    void recordingChanged();
    void attachmentsChanged();
    void mouthLevelChanged();
    void speakingChanged();
    void emotionChanged();
    void pcChanged();

private:
    void pcHandle(const QString &tp, const QJsonObject &o);
    void appendUser(const QString &text);
    void worker(const std::string &body);
    void workerHttp(const std::string &body);
    void workerVoiceToggle(const std::string &mode);
    QString systemPrompt() const;
    QString buildPayload(bool stream) const;

    // --- постоянное ws-соединение ---
    void wsLoop();
    void wsHandle(const QByteArray &payload);
    bool wsSend(const QByteArray &json);
    bool beginTurn(const QString &userText, const QByteArray &msgType);
    void finishTurn(bool cancelled, const QString &errText = QString());
    void playerLoop();
    void micLoop();
    void probeLoop();
    void abortPlayback();
    void setServices(bool brain, bool voice);

    // --- авто-переподключение (http-режим) ---
    void reconnectLoop();
    void requestReconnect();
    void setConnectionStatus(const QString &s);
    void setIsGenerating(bool on);

    QVector<QPair<QString, QString>> m_history;   // только http-режим
    double m_temperature = 0.7;
    int m_maxTokens = 8192;
    bool m_codeMode = false;
    bool m_voiceEnabled = false;
    std::atomic<bool> m_voiceBusy{false};
    QString m_status = QStringLiteral("Готов");
    QString m_speed = QStringLiteral("—");
    int m_lastTokens = 0;
    int m_totalTokensSpent = 0;
    int m_ctxTokens = -1;
    double m_stress = 0.0;
    bool m_isGenerating = false;
    QString m_connectionStatus = QStringLiteral("reconnecting");
    std::chrono::high_resolution_clock::time_point generationStartTime{};
    bool isFirstBatch = false;
    int m_reconnectAttempt = 0;
    std::atomic<bool> m_busy{false};
    std::atomic<bool> m_cancel{false};
    std::atomic<std::uintptr_t> m_socket{static_cast<std::uintptr_t>(~std::uintptr_t(0))};
    std::thread m_thread;
    std::atomic<bool> m_stopReconnect{false};
    std::atomic<bool> m_reconnectWanted{true};
    std::thread m_reconnectThread;
    bool m_wsMode = false;
    std::mutex m_cvMutex;
    std::condition_variable m_cv;

    // --- ws-режим ---
    std::thread m_wsThread;
    std::atomic<bool> m_wsStop{false};
    std::atomic<std::uintptr_t> m_wsSock{static_cast<std::uintptr_t>(~std::uintptr_t(0))};
    std::atomic<bool> m_wsUp{false};
    std::atomic<bool> m_historyReady{false};   // на сервере есть активная история (create-new-history сделан)
    QString m_activeHistory;                   // GUI-поток
    QString m_lastUserText;                    // GUI-поток
    // состояние текущего хода (под m_turnMx)
    std::mutex m_turnMx;
    bool m_turnActive = false;
    std::string m_answer;
    std::string m_pending;
    unsigned long m_lastFlush = 0;
    bool m_hadAudio = false;
    std::chrono::steady_clock::time_point m_t0{};
    bool m_gotFirst = false;
    // проигрыватель
    std::thread m_playThread;
    std::mutex m_playMx;
    std::condition_variable m_playCv;
    std::deque<QByteArray> m_playQ;
    bool m_playing = false;
    bool m_synthDone = false;
    std::atomic<bool> m_playAbort{false};
    std::atomic<std::uintptr_t> m_hwo{0};
    std::atomic<bool> m_playStop{false};
    // микрофон
    std::thread m_micThread;
    std::atomic<bool> m_micStop{false};
    bool m_recording = false;
    // вложения (GUI-поток)
    QStringList m_attachNames;
    QStringList m_attachData;   // data-URI
    QStringList m_attachMime;
    // уровень звука и «говорит»
    std::atomic<int> m_mouthA{0};        // 0..1000, пишет поток проигрывателя
    std::atomic<bool> m_speakA{false};
    double m_mouthLevel = 0;
    QString m_emotion = QStringLiteral("01");   // лицо Нейры; только GUI-поток
    bool m_speaking = false;
    qint64 m_speakHoldUntil = 0;
    QObject *m_levelTimer = nullptr;
    // управление ПК (GUI-поток)
    bool m_pcAvailable = false;
    bool m_pcEnabled = false;
    QString m_pcReason;
    QVariantMap m_pcConfirm;
    QVariantList m_pcActions;
    bool m_demo = false;
    // службы
    std::thread m_probeThread;
    bool m_brainUp = false;
    bool m_voiceUp = false;
};

#endif
