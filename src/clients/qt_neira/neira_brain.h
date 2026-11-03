// neira_brain.h — бэкенд Нейры для Qt/QML.
#ifndef NEIRA_BRAIN_H
#define NEIRA_BRAIN_H

#include <QObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QPair>
#include <string>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <cstdint>
#include <chrono>

class NeiraBrain : public QObject {
    Q_OBJECT
    Q_PROPERTY(double temperature READ temperature WRITE setTemperature NOTIFY temperatureChanged)
    Q_PROPERTY(int maxTokens READ maxTokens WRITE setMaxTokens NOTIFY maxTokensChanged)
    Q_PROPERTY(bool codeMode READ codeMode WRITE setCodeMode NOTIFY codeModeChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(int totalTokensSpent READ totalTokensSpent NOTIFY totalTokensSpentChanged)
    Q_PROPERTY(bool isGenerating READ isGenerating NOTIFY isGeneratingChanged)
    Q_PROPERTY(QString connectionStatus READ connectionStatus NOTIFY connectionStatusChanged)
    Q_PROPERTY(int reconnectAttempt READ reconnectAttempt NOTIFY reconnectAttemptChanged)

public:
    explicit NeiraBrain(QObject *parent = nullptr);
    ~NeiraBrain();

    double temperature() const { return m_temperature; }
    int maxTokens() const { return m_maxTokens; }
    bool codeMode() const { return m_codeMode; }
    QString status() const { return m_status; }
    QString speed() const { return m_speed; }
    int totalTokensSpent() const { return m_totalTokensSpent; }
    bool isGenerating() const { return m_isGenerating; }
    QString connectionStatus() const { return m_connectionStatus; }
    int reconnectAttempt() const { return m_reconnectAttempt; }

    void setTemperature(double t);
    void setMaxTokens(int n);
    void setCodeMode(bool on);

public slots:
    void sendMessage(const QString &text);
    void clearHistory();
    void stop();
    void saveSession(const QString &name);
    void loadSession(const QString &name);
    QStringList sessionList() const;

signals:
    void temperatureChanged();
    void maxTokensChanged();
    void codeModeChanged();
    void statusChanged();
    void speedChanged();
    void totalTokensSpentChanged();
    void isGeneratingChanged();
    void tokenReceived(const QString &delta);
    void responseFinished(const QString &full);
    void systemMessage(const QString &text);
    void historyLoaded(const QStringList &roles, const QStringList &texts);
    void connectionStatusChanged();
    void reconnectAttemptChanged();

private:
    void appendUser(const QString &text);
    void worker(const std::string &body);
    QString systemPrompt() const;
    QString buildPayload(bool stream) const;

    // --- авто-переподключение (Exponential Backoff) ---
    void reconnectLoop();
    void requestReconnect();
    void setConnectionStatus(const QString &s);
    void setIsGenerating(bool on);

    QVector<QPair<QString, QString>> m_history;
    double m_temperature = 0.7;
    int m_maxTokens = 8192;
    bool m_codeMode = false;
    QString m_status = QStringLiteral("Готов");
    QString m_speed = QStringLiteral("~0 t/s");
    int m_totalTokensSpent = 0;
    bool m_isGenerating = false;
    QString m_connectionStatus = QStringLiteral("reconnecting");
    // --- честный замер скорости: T0 фиксируется на первом батче ответа ---
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
    std::mutex m_cvMutex;
    std::condition_variable m_cv;
};

#endif
