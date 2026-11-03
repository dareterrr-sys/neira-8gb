// neira_gui.cpp — нативный Win32-клиент Нейры (v3: cyber-minimalism).
// Сборка: g++ -O2 -std=c++17 -municode neira_gui.cpp -o neira_gui.exe -lws2_32 -mwindows
//
// Дизайн (по советам): тёмная палитра, боковая панель настроек,
// статус-бар с указателем скорости t/s, поле ввода отдельной зоной,
// моноширинный шрифт в режиме кода.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>

#include <string>
#include <vector>
#include <sstream>
#include <cstdio>
#include <cstdlib>

#pragma comment(lib, "ws2_32.lib")

static const wchar_t *BRAIN_HOST = L"127.0.0.1";
static const int BRAIN_PORT = 8080;
static const wchar_t *BRAIN_PATH = L"/v1/chat/completions";
static const wchar_t *MODEL = L"brain";

static const UINT WM_APPEND_TEXT = WM_APP + 1;
static const UINT WM_REQUEST_DONE = WM_APP + 2;
static const UINT WM_UPDATE_SPEED = WM_APP + 3;

// элементы
enum {
    IDC_NEW = 101, IDC_CODE, IDC_TEMP_MINUS, IDC_TEMP_PLUS,
    IDC_CAP_MINUS, IDC_CAP_PLUS, IDC_SAVE, IDC_LOAD, IDC_SEND
};

// ---------- палитра (cyber-minimalism) ----------
static const COLORREF CLR_BKG    = RGB(13, 14, 21);     // #0d0e15
static const COLORREF CLR_PANEL  = RGB(18, 19, 28);     // #12131c
static const COLORREF CLR_INPUT  = RGB(27, 28, 40);
static const COLORREF CLR_TEXT    = RGB(255, 255, 255); // белый — ответы/код
static const COLORREF CLR_MUTED   = RGB(104, 107, 124); // #686b7c
static const COLORREF CLR_ACCENT  = RGB(0, 229, 255);   // #00e5ff
static const COLORREF CLR_HIST    = RGB(235, 236, 245);

// ---------- утилиты UTF-8 <-> UTF-16 ----------

static std::wstring utf8_to_utf16(const std::string &s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0);
    std::wstring out(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &out[0], n);
    return out;
}

static std::string utf16_to_utf8(const std::wstring &s) {
    if (s.empty()) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), (int)s.size(), &out[0], n, nullptr, nullptr);
    return out;
}

// ---------- JSON ----------

static std::string json_escape(const std::string &s) {
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

static std::string json_extract_string(const std::string &j, const std::string &key) {
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

// ---------- файлы (UTF-8) ----------

static bool write_file_utf8(const std::wstring &path, const std::string &data) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    BOOL ok = WriteFile(h, data.data(), (DWORD)data.size(), &written, nullptr);
    CloseHandle(h);
    return ok && written == (DWORD)data.size();
}

static std::string read_file_utf8(const std::wstring &path) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return "";
    DWORD size = GetFileSize(h, nullptr);
    std::string out(size, '\0');
    if (size > 0) {
        DWORD read = 0;
        ReadFile(h, &out[0], size, &read, nullptr);
        out.resize(read);
    }
    CloseHandle(h);
    return out;
}

// ---------- состояние ----------

struct ChatState {
    std::vector<std::pair<std::wstring, std::wstring>> history;
    double temperature = 0.7;
    int max_tokens = 8192;
    bool code_mode = false;

    std::wstring system_prompt() const {
        if (code_mode) {
            return L"Ты — инженер-исполнитель. Пишешь только код на C или C++ (не Python, "
                   L"не другие языки): без вступлений, без эмоций, без пояснений, "
                   L"без дублирования задания.";
        }
        return L"Ты — Нейра, ИИ-девушка, которая живёт в компьютере собеседника. "
               L"Отвечаешь по-русски, живо, но по делу.";
    }
};

static ChatState g_state;

static void append_history(const std::wstring &text);
static void update_panel_labels();
static void update_code_font();

static std::string build_payload(bool stream) {
    std::ostringstream o;
    o << "{\"model\":\"" << utf16_to_utf8(MODEL) << "\",\"messages\":[";
    for (size_t i = 0; i < g_state.history.size(); ++i) {
        if (i) o << ",";
        o << "{\"role\":\"" << utf16_to_utf8(g_state.history[i].first)
          << "\",\"content\":\"" << json_escape(utf16_to_utf8(g_state.history[i].second)) << "\"}";
    }
    o << "],\"temperature\":" << g_state.temperature
      << ",\"max_tokens\":" << g_state.max_tokens
      << ",\"stream\":" << (stream ? "true" : "false") << "}";
    return o.str();
}

static std::wstring session_path(const std::wstring &name) {
    return L"D:\\AI\\neira-tools\\saved\\gui_" + name + L".json";
}

static void save_session(const std::wstring &name) {
    std::ostringstream o;
    o << "[";
    for (size_t i = 0; i < g_state.history.size(); ++i) {
        if (i) o << ",";
        o << "{\"role\":\"" << utf16_to_utf8(g_state.history[i].first)
          << "\",\"content\":\"" << json_escape(utf16_to_utf8(g_state.history[i].second)) << "\"}";
    }
    o << "]";
    bool ok = write_file_utf8(session_path(name), o.str());
    append_history(ok ? L"— сессия сохранена —\r\n" : L"(не удалось сохранить сессию)\r\n");
}

static void load_session(const std::wstring &name) {
    std::string data = read_file_utf8(session_path(name));
    if (data.empty()) {
        append_history(L"(сессия не найдена)\r\n");
        return;
    }
    g_state.history.clear();
    size_t p = 0;
    while ((p = data.find("{\"role\":", p)) != std::string::npos) {
        std::string chunk = data.substr(p, data.find("},", p) - p + 1);
        std::string role = json_extract_string(chunk, "role");
        std::string content = json_extract_string(chunk, "content");
        g_state.history.push_back({utf8_to_utf16(role), utf8_to_utf16(content)});
        p = data.find("},", p);
        if (p == std::string::npos) break;
        p += 2;
    }
    if (g_state.history.empty()) {
        g_state.history.push_back({L"system", g_state.system_prompt()});
    }
    append_history(L"— сессия загружена: " + std::to_wstring(g_state.history.size()) + L" сообщ. —\r\n");
    update_panel_labels();
}

// ---------- HTTP/SSE ----------

struct RequestCtx {
    HWND hwnd;
    std::string body;
};

static volatile DWORD g_last_elapsed_ms = 0;
static volatile DWORD g_last_chars = 0;

static DWORD WINAPI WorkerThread(LPVOID param) {
    RequestCtx *ctx = (RequestCtx *)param;
    HWND hwnd = ctx->hwnd;
    std::string body = ctx->body;
    delete ctx;

    DWORD t0 = GetTickCount();

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return 1;
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) { WSACleanup(); return 1; }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)BRAIN_PORT);
    {
        char host8[64];
        WideCharToMultiByte(CP_UTF8, 0, BRAIN_HOST, -1, host8, sizeof host8, nullptr, nullptr);
        inet_pton(AF_INET, host8, &addr.sin_addr);
    }
    if (connect(s, (sockaddr *)&addr, sizeof addr) != 0) {
        closesocket(s); WSACleanup();
        PostMessage(hwnd, WM_APPEND_TEXT, 0, (LPARAM)(new std::wstring(L"(мозг не ответил — соединение не установлено)")));
        PostMessage(hwnd, WM_REQUEST_DONE, 0, (LPARAM)(new std::wstring(L"")));
        return 1;
    }

    {
        std::ostringstream req;
        std::string host8 = utf16_to_utf8(BRAIN_HOST);
        std::string path8 = utf16_to_utf8(BRAIN_PATH);
        req << "POST " << path8 << " HTTP/1.1\r\n"
            << "Host: " << host8 << ":" << BRAIN_PORT << "\r\n"
            << "Content-Type: application/json\r\n"
            << "Content-Length: " << body.size() << "\r\n"
            << "Connection: close\r\n\r\n"
            << body;
        std::string reqs = req.str();
        size_t sent = 0;
        while (sent < reqs.size()) {
            int n = send(s, reqs.data() + sent, (int)(reqs.size() - sent), 0);
            if (n <= 0) break;
            sent += (size_t)n;
        }
    }

    std::string raw;
    char buf[32768];
    int got;
    bool in_headers = true;
    bool ok = false;
    std::wstring full_answer;
    bool first_delta = true;
    DWORD last_speed_update = GetTickCount();
    size_t chars_so_far = 0;

    while ((got = recv(s, buf, sizeof buf, 0)) > 0) {
        raw.append(buf, (size_t)got);
        if (in_headers) {
            size_t h = raw.find("\r\n\r\n");
            if (h != std::string::npos) {
                std::string headers = raw.substr(0, h + 4);
                raw.erase(0, h + 4);
                in_headers = false;
                size_t sp1 = headers.find(' ');
                size_t sp2 = sp1 == std::string::npos ? std::string::npos : headers.find(' ', sp1 + 1);
                int status = 0;
                if (sp1 != std::string::npos && sp2 != std::string::npos) {
                    status = atoi(headers.substr(sp1 + 1, sp2 - sp1 - 1).c_str());
                }
                ok = status >= 200 && status < 300;
                if (!ok) {
                    std::wstring err = utf8_to_utf16("(мозг не ответил — код " + std::to_string(status) + ")");
                    PostMessage(hwnd, WM_APPEND_TEXT, 0, (LPARAM)(new std::wstring(err)));
                    closesocket(s); WSACleanup();
                    PostMessage(hwnd, WM_REQUEST_DONE, 0, (LPARAM)(new std::wstring(L"")));
                    return 1;
                }
            }
        }
        if (!in_headers && ok) {
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
                        closesocket(s); WSACleanup();
                        g_last_elapsed_ms = GetTickCount() - t0;
                        g_last_chars = (DWORD)full_answer.size();
                        PostMessage(hwnd, WM_REQUEST_DONE, 0, (LPARAM)(new std::wstring(full_answer)));
                        return 0;
                    }
                    std::string delta = json_extract_string(payload, "content");
                    if (!delta.empty()) {
                        if (first_delta) {
                            first_delta = false;
                            if (delta == "created" || delta.rfind("created", 0) == 0) {
                                continue;
                            }
                        }
                        full_answer += utf8_to_utf16(delta);
                        chars_so_far += delta.size();
                        // живая скорость: обновление каждые ~250 мс
                        DWORD now = GetTickCount();
                        if (now - last_speed_update >= 250) {
                            last_speed_update = now;
                            double elapsed = (double)(now - t0) / 1000.0;
                            if (elapsed > 0.05) {
                                int tps = (int)((double)chars_so_far / 4.0 / elapsed + 0.5);
                                PostMessage(hwnd, WM_UPDATE_SPEED, 0,
                                            (LPARAM)(new std::wstring(L"~" + std::to_wstring(tps) + L" t/s")));
                            }
                        }
                        PostMessage(hwnd, WM_APPEND_TEXT, 0, (LPARAM)(new std::wstring(utf8_to_utf16(delta))));
                    }
                }
            }
            raw.erase(0, start);
        }
    }
    closesocket(s);
    WSACleanup();
    g_last_elapsed_ms = GetTickCount() - t0;
    g_last_chars = (DWORD)full_answer.size();
    PostMessage(hwnd, WM_REQUEST_DONE, 0, (LPARAM)(new std::wstring(full_answer)));
    return 0;
}

// ---------- UI ----------

static HWND g_hwnd, g_hHistory, g_hInput, g_hSend, g_hStatus, g_hHint, g_hSpeed;
static HWND g_btnNew, g_btnCode, g_btnTempMinus, g_btnTempPlus;
static HWND g_btnCapMinus, g_btnCapPlus, g_btnSave, g_btnLoad;
static HWND g_hTempLabel, g_hCapLabel, g_hSideTitle;
static HFONT g_font, g_fontMono;
static WNDPROC g_oldInputProc = nullptr;
static bool g_busy = false;
static bool g_sidebar_visible = true;

static HBRUSH g_brBkg, g_brPanel, g_brInput;

static void set_status(const std::wstring &s) {
    SetWindowTextW(g_hStatus, s.c_str());
}

static void set_speed(const std::wstring &s) {
    SetWindowTextW(g_hSpeed, s.c_str());
}

static void set_busy(bool busy) {
    g_busy = busy;
    if (busy) {
        SetWindowTextW(g_hwnd, L"Нейра — печатает…");
        set_status(L"Печатает…");
    } else {
        SetWindowTextW(g_hwnd, L"Нейра — чат");
        set_status(L"Готов");
    }
}

static void update_panel_labels() {
    SetWindowTextW(g_hTempLabel, (L"Temp  " + std::to_wstring(g_state.temperature)).c_str());
    SetWindowTextW(g_hCapLabel, (L"Cap   " + std::to_wstring(g_state.max_tokens)).c_str());
}

static void update_code_font() {
    SendMessageW(g_hInput, WM_SETFONT, (WPARAM)(g_state.code_mode ? g_fontMono : g_font), TRUE);
}

static void append_history(const std::wstring &text) {
    int len = GetWindowTextLengthW(g_hHistory);
    SendMessageW(g_hHistory, EM_SETSEL, len, len);
    SendMessageW(g_hHistory, EM_REPLACESEL, FALSE, (LPARAM)text.c_str());
    SendMessageW(g_hHistory, EM_SETSEL, -1, -1);
    SendMessageW(g_hHistory, EM_SCROLLCARET, 0, 0);
}

static void append_history_role(const wchar_t *role, const std::wstring &text) {
    append_history(std::wstring(role) + L" " + text + L"\r\n");
}

static void send_current_message() {
    if (g_busy) {
        append_history(L"(подожди — ответ ещё идёт)\r\n");
        return;
    }
    int len = GetWindowTextLengthW(g_hInput);
    if (len <= 0) return;
    std::wstring text(len, L'\0');
    GetWindowTextW(g_hInput, &text[0], len + 1);

    if (!text.empty() && text[0] == L'/') {
        if (text == L"/new") {
            g_state.history.clear();
            g_state.history.push_back({L"system", g_state.system_prompt()});
            SetWindowTextW(g_hInput, L"");
            append_history(L"— история сброшена —\r\n");
            SetFocus(g_hInput);
            return;
        }
        if (text == L"/code" || text == L"/code on") {
            g_state.code_mode = true;
            g_state.temperature = 0.0;
            g_state.history.clear();
            g_state.history.push_back({L"system", g_state.system_prompt()});
            SetWindowTextW(g_hInput, L"");
            append_history(L"— режим кода включён —\r\n");
            SetWindowTextW(g_btnCode, L"Код: вкл");
            update_code_font();
            SetFocus(g_hInput);
            return;
        }
        if (text == L"/code off") {
            g_state.code_mode = false;
            g_state.temperature = 0.7;
            g_state.history.clear();
            g_state.history.push_back({L"system", g_state.system_prompt()});
            SetWindowTextW(g_hInput, L"");
            append_history(L"— режим кода выключен —\r\n");
            SetWindowTextW(g_btnCode, L"Код: выкл");
            update_code_font();
            SetFocus(g_hInput);
            return;
        }
        if (text == L"/ctx") {
            std::wstring info = L"— история: " + std::to_wstring(g_state.history.size())
                + L" сообщ.; температура: " + std::to_wstring(g_state.temperature)
                + L"; лимит: " + std::to_wstring(g_state.max_tokens)
                + L"; режим кода: " + (g_state.code_mode ? L"вкл" : L"выкл") + L" —\r\n";
            SetWindowTextW(g_hInput, L"");
            append_history(info);
            SetFocus(g_hInput);
            return;
        }
        if (text.rfind(L"/temp ", 0) == 0) {
            g_state.temperature = wcstod(text.c_str() + 6, nullptr);
            if (g_state.temperature < 0.0) g_state.temperature = 0.0;
            if (g_state.temperature > 2.0) g_state.temperature = 2.0;
            SetWindowTextW(g_hInput, L"");
            append_history(L"— температура: " + std::to_wstring(g_state.temperature) + L" —\r\n");
            update_panel_labels();
            SetFocus(g_hInput);
            return;
        }
        if (text.rfind(L"/cap ", 0) == 0) {
            g_state.max_tokens = _wtoi(text.c_str() + 5);
            if (g_state.max_tokens < 128) g_state.max_tokens = 128;
            if (g_state.max_tokens > 32768) g_state.max_tokens = 32768;
            SetWindowTextW(g_hInput, L"");
            append_history(L"— лимит: " + std::to_wstring(g_state.max_tokens) + L" —\r\n");
            update_panel_labels();
            SetFocus(g_hInput);
            return;
        }
        if (text.rfind(L"/save ", 0) == 0) {
            std::wstring name = text.substr(6);
            if (name.empty()) name = L"session";
            SetWindowTextW(g_hInput, L"");
            save_session(name);
            SetFocus(g_hInput);
            return;
        }
        if (text.rfind(L"/load ", 0) == 0) {
            std::wstring name = text.substr(6);
            if (name.empty()) name = L"session";
            SetWindowTextW(g_hInput, L"");
            load_session(name);
            SetFocus(g_hInput);
            return;
        }
        if (text == L"/exit") {
            PostMessageW(g_hwnd, WM_CLOSE, 0, 0);
            return;
        }
    }

    SetWindowTextW(g_hInput, L"");
    append_history_role(L"Вы:", text);

    if (g_state.history.empty()) {
        g_state.history.push_back({L"system", g_state.system_prompt()});
    }
    g_state.history.push_back({L"user", text});

    set_busy(true);
    set_speed(L"… t/s");
    std::string body = build_payload(true);
    RequestCtx *ctx = new RequestCtx{ g_hwnd, body };
    CreateThread(nullptr, 0, WorkerThread, ctx, 0, nullptr);
}

static LRESULT CALLBACK InputProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_KEYDOWN && wp == VK_RETURN) {
        if (!(GetKeyState(VK_SHIFT) & 0x8000)) {
            send_current_message();
            return 0;
        }
    }
    return CallWindowProcW(g_oldInputProc, hwnd, msg, wp, lp);
}

static void layout(HWND hwnd) {
    RECT rc;
    GetClientRect(hwnd, &rc);
    int w = rc.right - rc.left;
    int h = rc.bottom - rc.top;

    const int sidebar_w = g_sidebar_visible ? 200 : 0;
    const int status_h = 24;
    const int input_h = 56;
    const int gap = 8;

    // сайдбар
    int sx = sidebar_w > 0 ? gap : 0;
    int sy = 12;
    if (sidebar_w > 0) {
        MoveWindow(g_hSideTitle, sx, sy, sidebar_w - 2 * gap, 24, TRUE);
        sy += 30;
        MoveWindow(g_hTempLabel, sx, sy, sidebar_w - 2 * gap, 20, TRUE);
        sy += 24;
        MoveWindow(g_btnTempMinus, sx, sy, (sidebar_w - 3 * gap) / 2, 30, TRUE);
        MoveWindow(g_btnTempPlus, sx + (sidebar_w - 3 * gap) / 2 + gap, sy, (sidebar_w - 3 * gap) / 2, 30, TRUE);
        sy += 36;
        MoveWindow(g_hCapLabel, sx, sy, sidebar_w - 2 * gap, 20, TRUE);
        sy += 24;
        MoveWindow(g_btnCapMinus, sx, sy, (sidebar_w - 3 * gap) / 2, 30, TRUE);
        MoveWindow(g_btnCapPlus, sx + (sidebar_w - 3 * gap) / 2 + gap, sy, (sidebar_w - 3 * gap) / 2, 30, TRUE);
        sy += 44;
        int bw = sidebar_w - 2 * gap;
        MoveWindow(g_btnNew, sx, sy, bw, 32, TRUE); sy += 38;
        MoveWindow(g_btnCode, sx, sy, bw, 32, TRUE); sy += 38;
        MoveWindow(g_btnSave, sx, sy, bw, 32, TRUE); sy += 38;
        MoveWindow(g_btnLoad, sx, sy, bw, 32, TRUE);
    }

    // история
    MoveWindow(g_hHistory, sidebar_w, 0, w - sidebar_w, h - input_h - status_h, TRUE);

    // зона ввода + кнопка-стрелка
    int input_x = sidebar_w;
    int input_w = w - sidebar_w;
    int send_w = 44;
    MoveWindow(g_hInput, input_x + gap, h - input_h - status_h, input_w - send_w - 2 * gap, input_h - 2 * gap, TRUE);
    MoveWindow(g_hSend, input_x + input_w - send_w - gap, h - input_h - status_h + gap, send_w, input_h - 2 * gap, TRUE);

    // статус-строка: слева — статус, центр — подсказка, справа — скорость
    MoveWindow(g_hStatus, sidebar_w, h - status_h, 200, status_h, TRUE);
    MoveWindow(g_hHint, sidebar_w + 210, h - status_h, w - sidebar_w - 210 - 140, status_h, TRUE);
    MoveWindow(g_hSpeed, w - 130, h - status_h, 130, status_h, TRUE);
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CREATE: {
            g_hwnd = hwnd;
            g_font = CreateFontW(-15, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                                 DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                                 CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
            g_fontMono = CreateFontW(-15, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                                      DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                                      CLEARTYPE_QUALITY, FIXED_PITCH | FF_MODERN, L"Consolas");
            g_brBkg = CreateSolidBrush(CLR_BKG);
            g_brPanel = CreateSolidBrush(CLR_PANEL);
            g_brInput = CreateSolidBrush(CLR_INPUT);

            g_hSideTitle = CreateWindowW(L"STATIC", L"Настройки", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                         0, 0, 180, 24, hwnd, (HMENU)1, nullptr, nullptr);
            g_hTempLabel = CreateWindowW(L"STATIC", L"Temp", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                         0, 0, 170, 20, hwnd, (HMENU)2, nullptr, nullptr);
            g_hCapLabel = CreateWindowW(L"STATIC", L"Cap", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                        0, 0, 170, 20, hwnd, (HMENU)3, nullptr, nullptr);
            g_btnTempMinus = CreateWindowW(L"BUTTON", L"−", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                           0, 0, 80, 30, hwnd, (HMENU)IDC_TEMP_MINUS, nullptr, nullptr);
            g_btnTempPlus = CreateWindowW(L"BUTTON", L"+", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                          0, 0, 80, 30, hwnd, (HMENU)IDC_TEMP_PLUS, nullptr, nullptr);
            g_btnCapMinus = CreateWindowW(L"BUTTON", L"−", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                          0, 0, 80, 30, hwnd, (HMENU)IDC_CAP_MINUS, nullptr, nullptr);
            g_btnCapPlus = CreateWindowW(L"BUTTON", L"+", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                         0, 0, 80, 30, hwnd, (HMENU)IDC_CAP_PLUS, nullptr, nullptr);
            g_btnNew = CreateWindowW(L"BUTTON", L"Новый", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                     0, 0, 180, 32, hwnd, (HMENU)IDC_NEW, nullptr, nullptr);
            g_btnCode = CreateWindowW(L"BUTTON", L"Код: выкл", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                      0, 0, 180, 32, hwnd, (HMENU)IDC_CODE, nullptr, nullptr);
            g_btnSave = CreateWindowW(L"BUTTON", L"Сохранить", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                      0, 0, 180, 32, hwnd, (HMENU)IDC_SAVE, nullptr, nullptr);
            g_btnLoad = CreateWindowW(L"BUTTON", L"Загрузить", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                      0, 0, 180, 32, hwnd, (HMENU)IDC_LOAD, nullptr, nullptr);

            g_hHistory = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_MULTILINE |
                                       ES_AUTOVSCROLL | ES_READONLY | WS_VSCROLL,
                                       0, 0, 100, 100, hwnd, (HMENU)4, nullptr, nullptr);
            g_hInput = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_MULTILINE |
                                      ES_AUTOVSCROLL | WS_VSCROLL,
                                      0, 0, 100, 100, hwnd, (HMENU)5, nullptr, nullptr);
            g_hSend = CreateWindowW(L"BUTTON", L"→", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                    0, 0, 44, 40, hwnd, (HMENU)IDC_SEND, nullptr, nullptr);
            g_hStatus = CreateWindowW(L"STATIC", L"Готов", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                      0, 0, 200, 24, hwnd, (HMENU)6, nullptr, nullptr);
            g_hHint = CreateWindowW(L"STATIC", L"Enter — отправить · Shift+Enter — перенос строки",
                                    WS_CHILD | WS_VISIBLE | SS_LEFT,
                                    0, 0, 300, 24, hwnd, (HMENU)7, nullptr, nullptr);
            g_hSpeed = CreateWindowW(L"STATIC", L"~0 t/s", WS_CHILD | WS_VISIBLE | SS_RIGHT,
                                     0, 0, 130, 24, hwnd, (HMENU)8, nullptr, nullptr);

            for (HWND c : { g_hHistory, g_hInput, g_hSend, g_hStatus, g_hHint, g_hSpeed,
                            g_hSideTitle, g_hTempLabel, g_hCapLabel,
                            g_btnNew, g_btnCode, g_btnTempMinus, g_btnTempPlus,
                            g_btnCapMinus, g_btnCapPlus, g_btnSave, g_btnLoad }) {
                SendMessageW(c, WM_SETFONT, (WPARAM)g_font, TRUE);
            }

            g_oldInputProc = (WNDPROC)SetWindowLongPtrW(g_hInput, GWLP_WNDPROC, (LONG_PTR)InputProc);

            g_state.history.clear();
            g_state.history.push_back({L"system", g_state.system_prompt()});
            append_history(L"Нейра — нативный клиент v3.\r\n\r\n");
            update_panel_labels();
            update_code_font();
            return 0;
        }
        case WM_ERASEBKGND: {
            HDC hdc = (HDC)wp;
            RECT rc;
            GetClientRect(hwnd, &rc);
            if (g_brBkg) FillRect(hdc, &rc, g_brBkg);
            return 1;
        }
        case WM_SIZE:
            layout(hwnd);
            return 0;
        case WM_CTLCOLORSTATIC: {
            HDC hdc = (HDC)wp;
            HWND ctrl = (HWND)lp;
            if (ctrl == g_hStatus || ctrl == g_hHint || ctrl == g_hSpeed ||
                ctrl == g_hSideTitle || ctrl == g_hTempLabel || ctrl == g_hCapLabel) {
                SetTextColor(hdc, CLR_MUTED);
                SetBkColor(hdc, CLR_PANEL);
                return (LRESULT)g_brPanel;
            }
            SetTextColor(hdc, CLR_MUTED);
            SetBkColor(hdc, CLR_BKG);
            return (LRESULT)g_brBkg;
        }
        case WM_CTLCOLOREDIT: {
            HDC hdc = (HDC)wp;
            HWND ctrl = (HWND)lp;
            if (ctrl == g_hHistory) {
                SetTextColor(hdc, CLR_HIST);
                SetBkColor(hdc, CLR_BKG);
                return (LRESULT)g_brBkg;
            }
            SetTextColor(hdc, CLR_TEXT);
            SetBkColor(hdc, CLR_INPUT);
            return (LRESULT)g_brInput;
        }
        case WM_CTLCOLORBTN: {
            HDC hdc = (HDC)wp;
            SetTextColor(hdc, CLR_TEXT);
            SetBkColor(hdc, CLR_PANEL);
            return (LRESULT)g_brPanel;
        }
        case WM_COMMAND:
            switch (LOWORD(wp)) {
                case IDC_SEND:
                    send_current_message();
                    return 0;
                case IDC_NEW:
                    SetWindowTextW(g_hInput, L"/new");
                    send_current_message();
                    return 0;
                case IDC_CODE:
                    if (g_state.code_mode) {
                        SetWindowTextW(g_hInput, L"/code off");
                    } else {
                        SetWindowTextW(g_hInput, L"/code");
                    }
                    send_current_message();
                    return 0;
                case IDC_TEMP_MINUS: {
                    g_state.temperature -= 0.1;
                    if (g_state.temperature < 0.0) g_state.temperature = 0.0;
                    append_history(L"— температура: " + std::to_wstring(g_state.temperature) + L" —\r\n");
                    update_panel_labels();
                    return 0;
                }
                case IDC_TEMP_PLUS: {
                    g_state.temperature += 0.1;
                    if (g_state.temperature > 2.0) g_state.temperature = 2.0;
                    append_history(L"— температура: " + std::to_wstring(g_state.temperature) + L" —\r\n");
                    update_panel_labels();
                    return 0;
                }
                case IDC_CAP_MINUS: {
                    g_state.max_tokens /= 2;
                    if (g_state.max_tokens < 128) g_state.max_tokens = 128;
                    append_history(L"— лимит: " + std::to_wstring(g_state.max_tokens) + L" —\r\n");
                    update_panel_labels();
                    return 0;
                }
                case IDC_CAP_PLUS: {
                    g_state.max_tokens *= 2;
                    if (g_state.max_tokens > 32768) g_state.max_tokens = 32768;
                    append_history(L"— лимит: " + std::to_wstring(g_state.max_tokens) + L" —\r\n");
                    update_panel_labels();
                    return 0;
                }
                case IDC_SAVE:
                    save_session(L"session");
                    return 0;
                case IDC_LOAD:
                    load_session(L"session");
                    return 0;
            }
            break;
        case WM_APPEND_TEXT: {
            std::wstring *s = (std::wstring *)lp;
            if (s) { append_history(*s); delete s; }
            return 0;
        }
        case WM_UPDATE_SPEED: {
            std::wstring *s = (std::wstring *)lp;
            if (s) { set_speed(*s); delete s; }
            return 0;
        }
        case WM_REQUEST_DONE: {
            std::wstring *s = (std::wstring *)lp;
            if (s) {
                if (!s->empty()) {
                    g_state.history.push_back({L"assistant", *s});
                    append_history(L"\r\n\r\n");
                }
                delete s;
            }
            // скорость: ~4 символа ≈ 1 токен
            if (g_last_elapsed_ms > 0 && g_last_chars > 0) {
                int tps = (int)((double)g_last_chars / 4.0 / ((double)g_last_elapsed_ms / 1000.0) + 0.5);
                set_speed(L"~" + std::to_wstring(tps) + L" t/s");
            }
            set_busy(false);
            return 0;
        }
        case WM_DESTROY:
            DeleteObject(g_font);
            DeleteObject(g_fontMono);
            DeleteObject(g_brBkg);
            DeleteObject(g_brPanel);
            DeleteObject(g_brInput);
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int nCmdShow) {
    WNDCLASSW wc{};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = nullptr;
    wc.lpszClassName = L"NeiraGUI";
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowW(L"NeiraGUI", L"Нейра — чат",
                              WS_OVERLAPPEDWINDOW,
                              CW_USEDEFAULT, CW_USEDEFAULT, 1080, 720,
                              nullptr, nullptr, hInst, nullptr);
    if (!hwnd) return 1;

    ShowWindow(hwnd, nCmdShow);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
