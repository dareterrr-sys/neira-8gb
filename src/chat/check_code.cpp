// check_code.cpp — орган проверки кода (компиляция + ASan/UBSan + запуск).
// Принимает: check_code.exe <src.c> [--cc <компилятор>] [--timeout <мс>] [--no-asan]
// Выводит JSON: {ok, stage, exit_code, stdout, stderr, elapsed_ms}
// Построен по образцу органов slova.exe / edinicy.exe: отдельный CPU-процесс,
// не трогает видеопамять и генерацию токенов.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <chrono>
#include <algorithm>
#include <cctype>

static std::string w_to_u8(const std::wstring& w) {
    if (w.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

static std::wstring u8_to_w(const std::string& s) {
    if (s.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}

// Вывод cl.exe/link.exe приходит в OEM-кодировке консоли (cp866), а не в UTF-8:
// без перекодировки в JSON попадают кракозябры (03.11)
static bool valid_utf8(const std::string& s) {
    return s.empty() || MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.c_str(), (int)s.size(), nullptr, 0) > 0;
}

static std::string to_u8(const std::string& s) {
    if (valid_utf8(s)) return s;
    int n = MultiByteToWideChar(CP_OEMCP, 0, s.c_str(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_OEMCP, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w_to_u8(w);
}

// Есть ли в исходнике функция main: код из одной функции нечего запускать,
// и линковка без main падала с LNK1561 «не компилируется» (03.11)
static bool has_main(const std::string& src) {
    for (size_t p = src.find("main"); p != std::string::npos; p = src.find("main", p + 4)) {
        bool left = p == 0 || !(std::isalnum((unsigned char)src[p - 1]) || src[p - 1] == '_');
        size_t q = p + 4;
        while (q < src.size() && std::isspace((unsigned char)src[q])) ++q;
        if (left && q < src.size() && src[q] == '(') return true;
    }
    return false;
}

static std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) { char b[8]; std::snprintf(b, sizeof b, "\\u%04x", c); out += b; }
                else out += (char)c;
        }
    }
    return out;
}

static std::string quote(const std::string& s) {
    return "\"" + s + "\"";
}

static bool file_exists(const std::string& p) {
    DWORD a = GetFileAttributesW(u8_to_w(p).c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static bool ends_with(const std::string& s, const std::string& suf) {
    return s.size() >= suf.size() && s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

static std::string find_vcvars() {
    const char* cands[] = {
        "D:\\Programs\\VSBuildTools2022\\VC\\Auxiliary\\Build\\vcvars64.bat",
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat",
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Professional\\VC\\Auxiliary\\Build\\vcvars64.bat",
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build\\vcvars64.bat",
    };
    for (const char* c : cands) if (file_exists(c)) return c;
    return {};
}

static std::string find_cl_default() {
    std::string root = "D:\\Programs\\VSBuildTools2022\\VC\\Tools\\MSVC";
    std::string best;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(u8_to_w(root + "\\*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return {};
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
        std::string ver = w_to_u8(fd.cFileName);
        if (ver.empty() || ver[0] == '.') continue;
        std::string p = root + "\\" + ver + "\\bin\\Hostx64\\x64\\cl.exe";
        if (file_exists(p) && ver > best) best = ver;
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    if (best.empty()) return {};
    return root + "\\" + best + "\\bin\\Hostx64\\x64\\cl.exe";
}

static std::string read_file(const std::string& p, size_t cap, bool& truncated) {
    std::string out;
    truncated = false;
    HANDLE h = CreateFileW(u8_to_w(p).c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return out;
    char buf[65536];
    DWORD rd = 0;
    while (ReadFile(h, buf, sizeof buf, &rd, nullptr) && rd > 0) {
        if (out.size() + rd > cap) { truncated = true; out.append(buf, cap - out.size()); break; }
        out.append(buf, rd);
    }
    CloseHandle(h);
    return out;
}

struct RunResult {
    bool started = false;
    int exit_code = -1;
    std::string out, err;
    long long elapsed_ms = 0;
};

// Запуск процесса с перенаправлением stdout/stderr в файлы и таймаутом.
// Дочерние процессы убиваются через Job Object при выходе/таймауте.
static RunResult run_process(const std::string& cmdline, const std::string& cwd,
                             const std::string& out_file, const std::string& err_file,
                             DWORD timeout_ms) {
    RunResult r;
    // Job Object: при закрытии хендла убивает всех потомков
    HANDLE job = CreateJobObjectW(nullptr, nullptr);
    if (job) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = {};
        jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation, &jeli, sizeof jeli);
    }

    DeleteFileW(u8_to_w(out_file).c_str());
    DeleteFileW(u8_to_w(err_file).c_str());
    // Наследуемые дескрипторы: иначе дочерний процесс их не получит и вывод потеряется
    SECURITY_ATTRIBUTES sa = {};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    // Анонимные пайпы для stdout/stderr (как в subprocess): cmd/компиляторы
    // могут вести себя иначе с файловыми хендлами, пайпы надёжнее
    HANDLE hReadOut = nullptr, hWriteOut = nullptr;
    HANDLE hReadErr = nullptr, hWriteErr = nullptr;
    if (!CreatePipe(&hReadOut, &hWriteOut, &sa, 0) || !CreatePipe(&hReadErr, &hWriteErr, &sa, 0)) {
        r.err = "не удалось создать пайпы";
        return r;
    }
    SetHandleInformation(hWriteOut, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
    SetHandleInformation(hWriteErr, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
    HANDLE hIn = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);

    STARTUPINFOW si = {};
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.hStdOutput = hWriteOut;
    si.hStdError = hWriteErr;
    si.hStdInput = hIn;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi = {};
    std::wstring wcmd = u8_to_w(cmdline);
    std::wstring wcwd = u8_to_w(cwd);
    BOOL ok = CreateProcessW(nullptr, &wcmd[0], nullptr, nullptr, TRUE,
                             CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                             nullptr, wcwd.empty() ? nullptr : wcwd.c_str(), &si, &pi);
    if (!ok) {
        r.err = "CreateProcess не удался (код " + std::to_string(GetLastError()) + ")";
        CloseHandle(hWriteOut); CloseHandle(hWriteErr);
        CloseHandle(hReadOut); CloseHandle(hReadErr);
        if (hIn != INVALID_HANDLE_VALUE) CloseHandle(hIn);
        if (job) CloseHandle(job);
        return r;
    }
    if (job) AssignProcessToJobObject(job, pi.hProcess);

    // Write-концы пайпов закрываем сразу — иначе пайп не сигналит EOF
    CloseHandle(hWriteOut);
    CloseHandle(hWriteErr);

    auto t0 = std::chrono::steady_clock::now();
    DWORD wait = WaitForSingleObject(pi.hProcess, timeout_ms);
    auto t1 = std::chrono::steady_clock::now();
    r.elapsed_ms = (long long)std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

    if (wait == WAIT_TIMEOUT) {
        TerminateProcess(pi.hProcess, 1);
        r.exit_code = -9; // признак таймаута
        r.started = true;
    } else {
        DWORD code = 0;
        GetExitCodeProcess(pi.hProcess, &code);
        r.exit_code = (int)code;
        r.started = true;
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    // Читаем пайпы до EOF (вывод ограничен 6000 символов)
    char buf[65536];
    DWORD rd = 0;
    while (ReadFile(hReadOut, buf, sizeof buf, &rd, nullptr) && rd > 0) {
        if (r.out.size() + rd > 6000) { r.out.append(buf, 6000 - r.out.size()); r.out += "\n...[вывод обрезан]"; break; }
        r.out.append(buf, rd);
    }
    rd = 0;
    while (ReadFile(hReadErr, buf, sizeof buf, &rd, nullptr) && rd > 0) {
        if (r.err.size() + rd > 6000) { r.err.append(buf, 6000 - r.err.size()); r.err += "\n...[вывод обрезан]"; break; }
        r.err.append(buf, rd);
    }
    CloseHandle(hReadOut);
    CloseHandle(hReadErr);
    r.out = to_u8(r.out);
    r.err = to_u8(r.err);
    if (hIn != INVALID_HANDLE_VALUE) CloseHandle(hIn);
    if (job) CloseHandle(job); // убивает возможных потомков
    if (std::getenv("CHECK_DEBUG")) {
        std::fprintf(stderr, "[dbg] started=%d exit=%d elapsed=%lld out=%zu err=%zu files=(%s,%s)\n",
                     r.started ? 1 : 0, r.exit_code, r.elapsed_ms, r.out.size(), r.err.size(),
                     out_file.c_str(), err_file.c_str());
    }
    return r;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("{\"ok\":false,\"stage\":\"usage\",\"errors\":\"использование: check_code.exe <src.c> [--cc cc] [--timeout мс] [--no-asan]\"}\n");
        return 2;
    }
    std::string src;
    std::string cc;
    DWORD timeout_ms = 8000;
    bool asan = true;

    // Аргументы можно указывать в любом порядке; путь к исходнику — первый
    // не-опционный аргумент
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--cc" && i + 1 < argc) cc = argv[++i];
        else if (a == "--timeout" && i + 1 < argc) timeout_ms = (DWORD)std::atoi(argv[++i]);
        else if (a == "--no-asan") asan = false;
        else if (src.empty()) src = a;
    }

    if (!file_exists(src)) {
        std::printf("{\"ok\":false,\"stage\":\"input\",\"errors\":\"файл не найден: %s\"}\n", src.c_str());
        return 2;
    }

    // Выбор компилятора:
    //   --cc <путь> — явно (cl.exe → MSVC, иначе gcc-стиль);
    //   без --cc: MSVC cl (настоящий ASan), если найден vcvars; иначе w64devkit gcc.
    std::string compiler;
    bool msvc = false;
    auto set_compiler = [&](const std::string& p) {
        compiler = p;
        std::string lower = p;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        msvc = lower.find("cl.exe") != std::string::npos;
    };
    if (!cc.empty()) {
        set_compiler(cc);
    } else if (const char* e = std::getenv("CHECK_CC"); e && *e) {
        set_compiler(e);
    } else if (!find_vcvars().empty()) {
        std::string cl = find_cl_default();
        if (!cl.empty()) { set_compiler(cl); }
    }
    if (compiler.empty()) {
        if (file_exists("D:\\Programs\\w64devkit\\bin\\gcc.exe")) compiler = "D:\\Programs\\w64devkit\\bin\\gcc.exe";
        else compiler = "gcc";
    }

    // Экспортные пути: каталог компилятора нужен, чтобы дочерние exe находили
    // libasan.dll / clang_rt.asan_dynamic-x86_64.dll и т.п.
    std::string cc_dir = compiler.substr(0, compiler.find_last_of("\\/"));
    std::string env_path = std::getenv("PATH") ? std::getenv("PATH") : "";
    std::string new_path = cc_dir + ";" + env_path;
    SetEnvironmentVariableA("PATH", new_path.c_str());
    SetEnvironmentVariableA("VSLANG", "1033"); // английские диагностики cl, если пакет установлен
    SetEnvironmentVariableA("ASAN_OPTIONS", "detect_leaks=0");
    SetEnvironmentVariableA("UBSAN_OPTIONS", "print_stacktrace=1");

    wchar_t tmpBuf[MAX_PATH] = {};
    DWORD tmpLen = GetTempPathW(MAX_PATH, tmpBuf);
    std::string tmp = tmpLen ? w_to_u8(tmpBuf) : "C:\\Windows\\Temp";
    std::string stem = tmp + "neira_check_" + std::to_string(GetCurrentProcessId());
    std::string exe = stem + ".exe";

    bool truncated = false;
    const bool link = has_main(read_file(src, 4 << 20, truncated));
    std::string obj = stem + (msvc ? ".obj" : ".o");

    // --- Этап 1: компиляция (с ASan, при невозможности — без него) ---
    // Без main — только компиляция в объектный файл (/c, -c), запуска нет
    auto compile = [&](bool use_asan) {
        std::string cmd;
        if (msvc) {
            std::string vcvars = find_vcvars();
            if (vcvars.empty()) {
                RunResult bad;
                bad.err = "vcvars64.bat не найден";
                return bad;
            }
            std::string flags = "/nologo /std:c11 /W4 /Od /Zi /utf-8 /D_CRT_SECURE_NO_WARNINGS";
            if (use_asan) flags += " /fsanitize=address";
            // cl живёт внутри той же cmd-сессии, где вызван vcvars: окружение
            // (INCLUDE/LIB/PATH) применяется к cl автоматически.
            // Без внешних кавычек и /s: cmd сам разбирает операторы > и &&
            cmd = quote("cmd") + " /c " + "call " + quote(vcvars) +
                  " >nul 2>&1 && " + quote(compiler) + " " + flags + " " + quote(src) +
                  (link ? " /Fe:" + quote(exe) : " /c /Fo:" + quote(obj));
        } else {
            std::string flags = "-std=c11 -Wall -Wextra -O0 -g -fno-omit-frame-pointer";
            if (use_asan) flags += " -fsanitize=address,undefined";
            cmd = quote(compiler) + " " + flags + " " + quote(src) +
                  (link ? " -o " + quote(exe) : " -c -o " + quote(obj));
        }
        if (std::getenv("CHECK_DEBUG")) {
            std::fprintf(stderr, "[dbg] cmd: %s\n", cmd.c_str());
            if (msvc) std::fprintf(stderr, "[dbg] LIB=%s\n",
                                   std::getenv("LIB") ? std::getenv("LIB") : "(unset)");
        }
        return run_process(cmd, tmp, stem + ".cc.out", stem + ".cc.err", 60000);
    };

    std::string mode = "asan";
    RunResult comp = compile(asan);
    if (asan && (!comp.started || comp.exit_code != 0)) {
        // ASan-рантайм может отсутствовать (например, w64devkit без libasan):
        // смотрим, ссылается ли ошибка на библиотеки санитайзеров
        std::string diag = comp.err.empty() ? comp.out : comp.err;
        if (diag.find("-lasan") != std::string::npos ||
            diag.find("-lubsan") != std::string::npos ||
            diag.find("cannot find") != std::string::npos ||
            diag.find("sanitizer") != std::string::npos) {
            comp = compile(false);
            mode = "plain";
        }
    }
    if (!comp.started || comp.exit_code != 0) {
        std::string diag = comp.err.empty() ? comp.out : comp.err;
        std::printf("{\"ok\":false,\"stage\":\"compile\",\"mode\":\"%s\",\"compiler\":\"%s\",\"exit_code\":%d,\"errors\":\"%s\",\"elapsed_ms\":%lld}\n",
                    mode.c_str(), msvc ? "msvc" : "gcc", comp.exit_code, json_escape(diag).c_str(), comp.elapsed_ms);
        return 1;
    }
    if (!link) {
        std::string diag = comp.err.empty() ? comp.out : comp.err;
        std::printf("{\"ok\":true,\"stage\":\"compile\",\"mode\":\"%s\",\"compiler\":\"%s\",\"exit_code\":0,\"errors\":\"нет main: код только скомпилирован, не запускался\",\"stdout\":\"%s\",\"elapsed_ms\":%lld}\n",
                    mode.c_str(), msvc ? "msvc" : "gcc", json_escape(diag).c_str(), comp.elapsed_ms);
        DeleteFileW(u8_to_w(obj).c_str());
        DeleteFileW(u8_to_w(stem + ".pdb").c_str());
        return 0;
    }
    if (!file_exists(exe)) {
        std::printf("{\"ok\":false,\"stage\":\"compile\",\"mode\":\"%s\",\"compiler\":\"%s\",\"exit_code\":-1,\"errors\":\"исполняемый файл не создан\"}\n",
                    mode.c_str(), msvc ? "msvc" : "gcc");
        return 1;
    }

    // --- Этап 2: запуск под санитайзерами ---
    RunResult run = run_process(quote(exe), "C:\\", stem + ".out", stem + ".err", timeout_ms);
    if (!run.started) {
        std::printf("{\"ok\":false,\"stage\":\"run\",\"errors\":\"%s\"}\n", json_escape(run.err).c_str());
        return 2;
    }

    bool ok = (run.exit_code == 0);
    std::printf("{\"ok\":%s,\"stage\":\"run\",\"mode\":\"%s\",\"compiler\":\"%s\",\"exit_code\":%d,\"stdout\":\"%s\",\"stderr\":\"%s\",\"elapsed_ms\":%lld}\n",
                ok ? "true" : "false", mode.c_str(), msvc ? "msvc" : "gcc", run.exit_code,
                json_escape(run.out).c_str(), json_escape(run.err).c_str(), run.elapsed_ms);

    // Уборка временных файлов
    DeleteFileW(u8_to_w(exe).c_str());
    DeleteFileW(u8_to_w(stem + ".cc.out").c_str());
    DeleteFileW(u8_to_w(stem + ".cc.err").c_str());
    DeleteFileW(u8_to_w(stem + ".out").c_str());
    DeleteFileW(u8_to_w(stem + ".err").c_str());
    return ok ? 0 : 2;
}
