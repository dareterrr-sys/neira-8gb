// neira_chat_cli.cpp — C++ текстовый клиент Нейры (полная версия).
// Сборка: g++ -O2 -std=c++17 neira_chat_cli.cpp -o neira_chat_cli.exe -lws2_32
//
// Возможности:
//  - SSE-стриминг ответа мозга (stream:true), живой вывод, без «обрывов»;
//  - многострочные вставки: склейка по «окну тишины» 250 мс;
//  - режим кода: строгий промпт, temperature=0, извлечение кода;
//  - /check: полный вывод органа check_code.exe (stdout+stderr через файл,
//    наследуемые дескрипторы, таймаут, TerminateProcess);
//  - сессии: честный JSON-парсер с unescape;
//  - команды: /help /exit /new /sys /prompt /temp /cap /code /check
//    /save /load /session-save /session-load /ctx;
//  - без автопродолжения: /cont остаётся только для ручного продолжения.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <cctype>
#include <iterator>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <chrono>
#include <thread>

using namespace std;

static string read_file(const string &path);

static const char *BRAIN_HOST = "127.0.0.1";
static const int BRAIN_PORT = 8080;
static const char *BRAIN_PATH = "/v1/chat/completions";
static const char *MODEL = "brain";
static const int IDLE_MS = 250;
static const int CHECK_TIMEOUT_MS = 60000;

static const string SAVED_DIR = "D:\\AI\\neira-tools\\saved\\";
static const string SESS_DIR = "D:\\AI\\neira-tools\\sessions\\";
static const string CHECK_EXE = "D:\\AI\\neira-tools\\check_code.exe";

static bool g_confirm_multiline = true;   // подтверждать Enterом многострочные вставки

// ---------- JSON helpers ----------

static string json_escape(const string &s) {
    string r;
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
                    // экранируем остальные управляющие символы (включая NUL)
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

// значение строки из JSON (с обработкой escape)
static string json_extract_string(const string &j, const string &key) {
    string needle = "\"" + key + "\"";
    size_t p = j.find(needle);
    if (p == string::npos) return "";
    p = j.find(':', p + needle.size());
    if (p == string::npos) return "";
    p = j.find('"', p);
    if (p == string::npos) return "";
    ++p;
    string out;
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

static string unescape_json(const string &s) {
    string out;
    for (size_t p = 0; p < s.size(); ++p) {
        if (s[p] == '\\' && p + 1 < s.size()) {
            char n = s[++p];
            switch (n) {
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case '"':  out += '"'; break;
                case '\\': out += '\\'; break;
                default: out += n;
            }
        } else {
            out += s[p];
        }
    }
    return out;
}

// ---------- HTTP / SSE ----------

struct HttpResult {
    bool ok = false;
    string body;
    int status = 0;
};

static HttpResult http_post_stream(const string &body, bool stream,
                                   const function<bool(const string &)> &on_delta) {
    HttpResult res;
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return res;
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) { WSACleanup(); return res; }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)BRAIN_PORT);
    inet_pton(AF_INET, BRAIN_HOST, &addr.sin_addr);
    if (connect(s, (sockaddr *)&addr, sizeof addr) != 0) {
        closesocket(s); WSACleanup(); return res;
    }

    ostringstream req;
    req << "POST " << BRAIN_PATH << " HTTP/1.1\r\n"
        << "Host: " << BRAIN_HOST << ":" << BRAIN_PORT << "\r\n"
        << "Content-Type: application/json\r\n"
        << "Content-Length: " << body.size() << "\r\n"
        << "Connection: close\r\n\r\n"
        << body;

    string reqs = req.str();
    size_t sent = 0;
    while (sent < reqs.size()) {
        int n = send(s, reqs.data() + sent, (int)(reqs.size() - sent), 0);
        if (n <= 0) { closesocket(s); WSACleanup(); return res; }
        sent += (size_t)n;
    }

    string raw, headers;
    bool in_headers = true;
    char buf[32768];
    int got;
    while ((got = recv(s, buf, sizeof buf, 0)) > 0) {
        raw.append(buf, (size_t)got);
        if (in_headers) {
            size_t h = raw.find("\r\n\r\n");
            if (h != string::npos) {
                headers = raw.substr(0, h + 4);
                raw.erase(0, h + 4);
                in_headers = false;
                // парсим код ответа: "HTTP/1.1 200 OK"
                size_t sp1 = headers.find(' ');
                size_t sp2 = sp1 == string::npos ? string::npos : headers.find(' ', sp1 + 1);
                if (sp1 != string::npos && sp2 != string::npos) {
                    res.status = atoi(headers.substr(sp1 + 1, sp2 - sp1 - 1).c_str());
                }
                res.ok = res.status >= 200 && res.status < 300;
                if (!res.ok) {
                    // ошибка: дочитываем тело как есть (это не SSE)
                    res.body = raw;
                    if (!stream) break;
                    continue;
                }
            }
        }
        if (!in_headers) {
            if (stream) {
                // разбираем SSE: строки "data: {...}"
                size_t start = 0;
                while (true) {
                    size_t nl = raw.find('\n', start);
                    if (nl == string::npos) break;
                    string line = raw.substr(start, nl - start);
                    start = nl + 1;
                    if (line.rfind("data:", 0) == 0) {
                        string payload = line.substr(5);
                        // убрать возможный \r
                        while (!payload.empty() && (payload.back() == '\r' || payload.back() == ' ')) payload.pop_back();
                        if (payload.find("[DONE]") != string::npos) {
                            closesocket(s); WSACleanup();
                            res.ok = true;
                            return res;
                        }
                        string delta = json_extract_string(payload, "content");
                        if (!delta.empty()) {
                            res.body += delta;
                            if (on_delta) on_delta(delta);
                        }
                        string err = json_extract_string(payload, "message");
                        if (!err.empty() && res.body.empty()) res.body = err;
                    }
                }
                raw.erase(0, start);
            } else {
                res.body = raw;
            }
        }
    }
    if (in_headers) { res.ok = false; }
    if (!stream && res.ok) res.body = raw;
    closesocket(s);
    WSACleanup();
    return res;
}

// ---------- check_code.exe с полным захватом вывода ----------

static string run_check(const string &src_path) {
    string cmd = "\"" + CHECK_EXE + "\" \"" + src_path + "\" --timeout 60000";

    string out_path = SAVED_DIR + "_check_out.txt";
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof sa;
    sa.bInheritHandle = TRUE;

    HANDLE hOut = CreateFileA(out_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ,
                              &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hOut == INVALID_HANDLE_VALUE) return "{\"ok\":false,\"errors\":\"cannot create out file\"}";

    STARTUPINFOA si{};
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = hOut;
    si.hStdError = hOut;

    PROCESS_INFORMATION pi{};
    BOOL ok = CreateProcessA(nullptr, &cmd[0], nullptr, nullptr, TRUE,
                             0, nullptr, nullptr, &si, &pi);
    if (!ok) {
        CloseHandle(hOut);
        return "{\"ok\":false,\"errors\":\"CreateProcess failed\"}";
    }

    DWORD wait = WaitForSingleObject(pi.hProcess, CHECK_TIMEOUT_MS);
    if (wait == WAIT_TIMEOUT) {
        TerminateProcess(pi.hProcess, 1);
        WaitForSingleObject(pi.hProcess, 5000);
    }
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    CloseHandle(hOut);

    string out = read_file(out_path);
    if (out.empty()) out = "{\"ok\":false,\"errors\":\"empty organ output\"}";
    return out;
}

// ---------- консоль и файлы ----------

static void set_utf8_console() {
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
}

static string read_file(const string &path) {
    ifstream f(path, ios::binary);
    if (!f) return "";
    ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static bool write_file(const string &path, const string &data) {
    ofstream f(path, ios::binary);
    if (!f) return false;
    f << data;
    return true;
}

// ---------- состояние ----------

struct ChatState {
    vector<pair<string, string>> history;
    double temperature = 0.7;
    int max_tokens = 8192;
    bool code_mode = false;
    string saved_code;
    string last_answer;

    string system_prompt() const {
        if (code_mode) {
            return "Ты — инженер-исполнитель. Пишешь только код: без вступлений, "
                   "без эмоций, без пояснений, без дублирования задания. Отвечаешь "
                   "ровно тем, что просили.";
        }
        // общая текстовая персона всех чат-клиентов (03.11), запасная строка — если файла нет
        static const string persona = [] {
            std::ifstream f("D:\\AI\\neira-tools\\neira_persona.txt", std::ios::binary);
            std::string s((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
            while (!s.empty() && std::isspace((unsigned char)s.back())) s.pop_back();
            return s;
        }();
        if (!persona.empty()) return persona;
        return "Ты — Нейра, ИИ-девушка, которая живёт в компьютере собеседника. "
               "Отвечаешь по-русски, живо, но по делу.";
    }
};

static void trim_history(vector<pair<string, string>> &h) {
    if (h.size() <= 21) return;
    vector<pair<string, string>> trimmed;
    trimmed.push_back(h[0]);
    for (size_t i = h.size() - 20; i < h.size(); ++i) trimmed.push_back(h[i]);
    h.swap(trimmed);
}

static string extract_code_block(const string &s) {
    string fence = "```";
    size_t a = s.find(fence);
    if (a == string::npos) return s;
    a = s.find('\n', a);
    if (a == string::npos) return s;
    ++a;
    size_t b = s.find(fence, a);
    if (b == string::npos) b = s.size();
    string code = s.substr(a, b - a);
    while (!code.empty() && (code.back() == '\n' || code.back() == '\r' || code.back() == ' ')) code.pop_back();
    return code;
}

static string build_payload(const vector<pair<string, string>> &msgs,
                            double temperature, int max_tokens, bool stream) {
    ostringstream o;
    o << "{\"model\":\"" << MODEL << "\",\"messages\":[";
    for (size_t i = 0; i < msgs.size(); ++i) {
        if (i) o << ",";
        o << "{\"role\":\"" << msgs[i].first << "\",\"content\":\""
          << json_escape(msgs[i].second) << "\"}";
    }
    o << "],\"temperature\":" << temperature
      << ",\"max_tokens\":" << max_tokens
      << ",\"stream\":" << (stream ? "true" : "false") << "}";
    return o.str();
}

// ---------- команды ----------

static void print_help() {
    cout << "Команды:\n"
         << "  /exit — выйти\n"
         << "  /new — сбросить историю\n"
         << "  /sys <текст> — сменить системный промпт (кроме режима кода)\n"
         << "  /prompt — показать текущий системный промпт\n"
         << "  /temp <число> — температура (0.0–2.0)\n"
         << "  /confirm [on|off] — требовать /send перед отправкой собранного сообщения\n"
         << "  /send — отправить собранное сообщение (вместо Enter)\n"
         << "  /cap <N> — лимит токенов на ответ\n"
         << "  /code [on|off] — режим кода (строгий промпт, temp=0)\n"
         << "  /check — проверить последний код органом check_code.exe\n"
         << "  /save [имя] — сохранить последний код в saved/\n"
         << "  /load <путь> — отправить содержимое файла как сообщение\n"
         << "  /session-save [имя] — сохранить историю в sessions/\n"
         << "  /session-load [имя] — загрузить историю из sessions/\n"
         << "  /ctx — состояние: история, температура, лимит\n"
         << "  /help — этот список\n";
}

static bool handle_command(ChatState &st, const string &line, bool &exit_flag,
                           bool &want_send) {
    if (line == "/exit") { exit_flag = true; return true; }
    if (line == "/new") {
        st.history.clear();
        st.saved_code.clear();
        st.last_answer.clear();
        cout << "(история сброшена)\n";
        return true;
    }
    if (line == "/help") { print_help(); return true; }
    if (line.rfind("/sys ", 0) == 0) {
        string sys = line.substr(5);
        st.history.clear();
        st.history.push_back({"system", sys});
        cout << "(системный промпт сменён)\n";
        return true;
    }
    if (line == "/prompt") {
        cout << st.system_prompt() << "\n";
        return true;
    }
    if (line.rfind("/ctx ", 0) == 0) {
        st.temperature = atof(line.c_str() + 5);
        cout << "(температура: " << st.temperature << ")\n";
        return true;
    }
    if (line == "/confirm" || line.rfind("/confirm ", 0) == 0) {
        string arg = line.length() > 8 ? line.substr(9) : "on";
        g_confirm_multiline = (arg != "off");
        cout << "(подтверждение многострочных вставок: "
             << (g_confirm_multiline ? "вкл" : "выкл") << ")\n";
        return true;
    }
    if (line.rfind("/cap ", 0) == 0) {
        st.max_tokens = atoi(line.c_str() + 5);
        cout << "(лимит: " << st.max_tokens << ")\n";
        return true;
    }
    if (line == "/code" || line.rfind("/code ", 0) == 0) {
        string arg = line.length() > 5 ? line.substr(6) : "on";
        st.code_mode = (arg != "off");
        if (st.code_mode) st.temperature = 0.0;
        // синхронизируем системный промпт в истории
        if (!st.history.empty() && st.history[0].first == "system") {
            st.history[0].second = st.system_prompt();
        } else {
            st.history.insert(st.history.begin(), {"system", st.system_prompt()});
        }
        cout << "(режим кода: " << (st.code_mode ? "вкл" : "выкл") << ")\n";
        return true;
    }
    if (line == "/check") {
        if (st.saved_code.empty()) {
            cout << "(нет сохранённого кода — сначала попроси Нейру написать код)\n";
            return true;
        }
        string path = SAVED_DIR + "_last_code.c";
        write_file(path, st.saved_code);
        string verdict = run_check(path);
        cout << verdict << "\n";
        return true;
    }
    if (line == "/save" || line.rfind("/save ", 0) == 0) {
        string name = line.length() > 5 ? line.substr(6) : "_last_code";
        string path = SAVED_DIR + name;
        write_file(path, st.saved_code);
        cout << "(сохранено: " << path << ")\n";
        return true;
    }
    if (line.rfind("/load ", 0) == 0) {
        string path = line.substr(6);
        string content = read_file(path);
        if (content.empty()) {
            cout << "(файл не прочитан: " << path << ")\n";
        } else {
            if (st.history.empty()) st.history.push_back({"system", st.system_prompt()});
            st.history.push_back({"user", content});
            cout << "(файл отправлен как сообщение)\n";
            want_send = true;   // сразу отправляем загруженный текст
        }
        return true;
    }
    if (line == "/session-save" || line.rfind("/session-save ", 0) == 0) {
        string name = line.length() > 13 ? line.substr(14) : "session";
        string path = SESS_DIR + name + ".json";
        ostringstream o;
        o << "[";
        for (size_t i = 0; i < st.history.size(); ++i) {
            if (i) o << ",";
            o << "{\"role\":\"" << st.history[i].first
              << "\",\"content\":\"" << json_escape(st.history[i].second) << "\"}";
        }
        o << "]";
        write_file(path, o.str());
        cout << "(сессия сохранена: " << path << ")\n";
        return true;
    }
    if (line == "/session-load" || line.rfind("/session-load ", 0) == 0) {
        string name = line.length() > 13 ? line.substr(14) : "session";
        string path = SESS_DIR + name + ".json";
        string data = read_file(path);
        if (data.empty()) {
            cout << "(сессия не найдена: " << path << ")\n";
            return true;
        }
        st.history.clear();
        size_t p = 0;
        while ((p = data.find("{\"role\":", p)) != string::npos) {
            string chunk = data.substr(p, data.find("},", p) - p + 1);
            string role = json_extract_string(chunk, "role");
            string content = json_extract_string(chunk, "content");
            st.history.push_back({role, unescape_json(content)});
            p = data.find("},", p);
            if (p == string::npos) break;
            p += 2;
        }
        if (st.history.empty()) {
            cout << "(сессия пуста или повреждена)\n";
        } else {
            cout << "(сессия загружена: " << st.history.size() << " сообщ.)\n";
        }
        return true;
    }
    if (line == "/ctx") {
        cout << "история: " << st.history.size() << " сообщ.; температура: "
             << st.temperature << "; лимит: " << st.max_tokens
             << "; режим кода: " << (st.code_mode ? "вкл" : "выкл") << "\n";
        return true;
    }
    return false;
}

// ---------- главный цикл ----------

// разбивает ввод на логические строки, нормализуя \r\n и \r -> \n
// пустые строки сохраняются (абзацы)
static vector<string> split_lines(const string &s) {
    vector<string> out;
    string norm;
    norm.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\r') {
            if (i + 1 < s.size() && s[i + 1] == '\n') ++i;
            norm += '\n';
        } else {
            norm += s[i];
        }
    }
    size_t pos;
    while ((pos = norm.find('\n')) != string::npos) {
        out.push_back(norm.substr(0, pos));
        norm.erase(0, pos + 1);
    }
    out.push_back(norm);
    return out;
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    set_utf8_console();

    if (argc > 1) {
        // необязательные переопределения: хост порт
        // (пока только для будущего использования)
    }

    ChatState st;
    st.history.push_back({"system", st.system_prompt()});

    cout << "Нейра (C++ клиент, SSE). Мозг: " << BRAIN_HOST << ":" << BRAIN_PORT << "\n";
    cout << "Команды: /help для списка.\n";

    bool exit_flag = false;
    string pending;
    bool have_pending = false;

    auto send_message = [&]() {
        have_pending = false;
        pending.clear();
        trim_history(st.history);

        string payload = build_payload(st.history, st.temperature, st.max_tokens, true);
        cout << "\nНейра: ";
        cout.flush();

        string answer;
        bool ok = false;
        int status = 0;
        for (int attempt = 1; attempt <= 4; ++attempt) {
            try {
                bool first_delta = true;
                HttpResult r = http_post_stream(payload, true, [&](const string &d) -> bool {
                    if (first_delta && d == "created") {
                        first_delta = false;   // пропускаем мусорный токен стриминга
                        return true;
                    }
                    first_delta = false;
                    cout << d;
                    cout.flush();
                    return true;
                });
                ok = r.ok;
                status = r.status;
                answer = r.body;
            } catch (...) {
                ok = false;
            }
            if (ok && !answer.empty()) break;
            if (status == 503 || status == 429 || status == 0) {
                cout << "\n(мозг занят, код " << status << " — повтор через 3 с, попытка "
                     << attempt << "/4)";
                cout.flush();
                this_thread::sleep_for(chrono::seconds(3));
                continue;
            }
            break;
        }

        if (!ok || answer.empty()) {
            string sample = answer.substr(0, 300);
            cout << "\n(мозг не ответил — код " << status
                 << "; запущен ли мозг на " << BRAIN_HOST
                 << ":" << BRAIN_PORT << "?)\n";
            if (!sample.empty()) {
                cout << "  тело ошибки: " << sample << "\n";
            }
            return;
        }

        st.history.push_back({"assistant", answer});
        st.last_answer = answer;

        if (st.code_mode) {
            st.saved_code = extract_code_block(answer);
        }
        cout << "\n\n";
    };

    while (!exit_flag) {
        string line;
        if (!getline(cin, line)) break;

        vector<string> parts = split_lines(line);

        if (!have_pending) {
            // не в режиме сбора: команды обрабатываются сразу
            if (!parts.empty() && parts[0] == "/send") {
                cout << "(нечего отправлять)\n";
                continue;
            }
            if (!parts.empty() && parts[0] == "/cancel") {
                cout << "(нечего отменять)\n";
                continue;
            }
            if (!parts.empty() && !parts[0].empty() && parts[0][0] == '/') {
                bool want_send = false;
                if (handle_command(st, parts[0], exit_flag, want_send)) {
                    if (want_send) send_message();
                    continue;
                }
            }
            // начало сбора сообщения (все части, включая пустые абзацы)
            pending = parts[0];
            have_pending = true;
            for (size_t i = 1; i < parts.size(); ++i) {
                pending += "\n" + parts[i];
            }
            if (g_confirm_multiline) {
                size_t n = 1;
                for (char c : pending) if (c == '\n') ++n;
                cout << "\n[собрано " << n << " строк (" << pending.size()
                     << " симв.); /send — отправить; /cancel — отменить]\n";
                cout.flush();
            } else {
                st.history.push_back({"user", pending});
                send_message();
            }
            continue;
        }

        // есть собранное сообщение
        if (parts.size() == 1 && parts[0] == "/cancel") {
            have_pending = false;
            pending.clear();
            cout << "(вставка отменена)\n";
            continue;
        }
        if (parts.size() == 1 && parts[0] == "/send") {
            st.history.push_back({"user", pending});
            send_message();
            continue;
        }
        for (size_t i = 0; i < parts.size(); ++i) {
            pending += "\n" + parts[i];
        }
        size_t n = 1;
        for (char c : pending) if (c == '\n') ++n;
        cout << "[собрано " << n << " строк (" << pending.size()
             << " симв.); /send — отправить; /cancel — отменить]\n";
        cout.flush();
    }

    WSACleanup();
    return 0;
}
