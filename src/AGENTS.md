# AGENTS.md — D:\AI (рабочий стол Нейры)

Рабочая папка локального ИИ-компаньона «Нейра» — НЕ единый репозиторий (не git).
Подпроекты: `neira-tools/` (чат-CLI, органы, GUI), `llama-neira-hot/` (мозг),
`Open-LLM-VTuber/` (голосовое приложение), `voices/server/` (голос),
`expert-map/`, `ik_llama.cpp/`, `gguf/` (модели), `_Документы/` (vault Obsidian:
Журналы, Сессии, Концепции, Планы, Заметки; индекс — `_Документы\Индекс.md`,
`_Документы\README.md`; план — `_Документы\Планы\REPO_PLAN.md`; журнал —
`_Документы\Журналы\Журнал исследований Нейры.docx`, не md).

## Мозг (llama-server)

- Бинарь: `D:\AI\llama-neira-hot\llama-server.exe` (наша сборка llama.cpp); модель
  `gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`; порт 8080, alias `brain`,
  API `http://127.0.0.1:8080/v1` (OpenAI-совместимый).
- Запуск: `Neira-start.bat` (голос+мозг+приложение), `Neira-chat.bat`
  (мозг+CLI), `Neira-gui.bat` (мозг+нативный GUI). Конфиги мозга:
  `llama-neira-hot/brain-v40.bat` (32k, `-ub 2048`) и `brain-v40-live.bat`
  (16k, `-ub 512`, резерв VRAM 700 МБ).
- **Порядок запуска важен**: мозг при старте замеряет свободную VRAM и по ней
  размеряет пул горячих экспертов (`hot_experts.bin`) — голос запускать ДО мозга.
  `Neira-start.bat` сам выбирает `brain-v40` vs `brain-v40-live` по `tts_model`
  в `Open-LLM-VTuber/conf.yaml` (значение `openai_tts` → live-режим).
- Проверка: `Invoke-RestMethod http://127.0.0.1:8080/health` (status ok);
  ждать появления в `.bat`-файлах через `curl -s ... | find "ok"`.
- Перезапуск после правки `.bat`: `taskkill /IM llama-server.exe /F` (разрешён —
  автор разрешил перезапускать/выключать свои запущенные файлы, см. «Поведение»)
  + запустить bat заново; проверить CommandLine
  процесса: обязательны `--reasoning off` и `-n <N_PREDICT>` (по умолчанию 16384).
- Ловушки:
  - **ДВА мозга конфликтуют на 8080**: старый `llama-server.bat` (это
    Qwen3-VL-30B с жёстким `-n 1536`, alias `qwen3-vl`) и `brain-v40.bat`.
    Если старый запущен — новый не поднимется, а ответы обрежутся на ~1536 токенах.
  - KV cache shifting на нашем билде не работает: переполнение контекста = ошибка
    запроса, а не сдвиг (флаг `--context-shift` в bat есть, но не спасает).
  - `--chat-template-kwargs` устарел; используется `--reasoning off`.
  - Разогрев после холодного старта: `voices/server/warm_brain.py` (залия модели в
    OS-кэш + длинный разовый промпт) запускается в фоне из `Neira-start.bat` /
    `Neira-chat.bat` — без него первый ответ читает ~20 ГБ экспертов с диска.

## Чат-клиент (`neira-tools/neira_chat_cli.py`)

- Запуск: `D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe neira_chat_cli.py`.
  Команды: `/help /exit /new /sys /prompt /rules /ctx /code /cap /temp /check
  /autofix /dict /save /load /session-save /session-load`.
- Многострочная вставка (Ctrl+V) склеивается по «окну тишины» 250 мс между
  строками (`neira_chat_cli.py` ~строки 103–126); команды `/…` — только
  одиночные строки.
- Сессии: `/session-save [имя]` / `/session-load [имя]` →
  `neira-tools/sessions/`; `/save [имя]` → `neira-tools/saved/`;
  `/load <путь>` шлёт файл сообщением.
- Персона: `Open-LLM-VTuber/conf.yaml` → `character_config.persona_prompt`.
  Правила поведения: `neira-tools/neira_behavior_rules.json`; защита: правило
  >200 символов не сохраняется (`neira_behavior.py` ~строка 70). Паттерны
  срабатывают на «никогда/всегда/не…» — осторожно с длинными сообщениями.
- Автопродолжение: при обрыве клиент шлёт хвост ответа (~400 символов); если
  модель повторно начинает с «Вот полная реализация…» — клиент останавливается
  (детектор RESTART_RE).

## Орган проверки кода (`neira-tools/check_code.exe`)

- Компилирует `.c`, гоняет под ASan/UBSan с таймаутом, возвращает JSON
  `{ok, stage, mode, compiler, exit_code, errors, stdout, stderr, elapsed_ms}`.
- Вызов: `check_code.exe <src.c> [--cc <путь>] [--timeout <мс>] [--no-asan]`.
- По умолчанию MSVC `cl.exe` (VSBuildTools2022) с настоящим ASan; откат
  на w64devkit gcc (mode=plain).
- Грабли (не ломать заново):
  - перенаправление вывода требует наследуемых дескрипторов
    (SECURITY_ATTRIBUTES с bInheritHandle=TRUE), иначе вывод теряется;
  - cl пишет диагностики в STDOUT — всегда объединять оба потока;
  - cl запускать в той же cmd-сессии, где вызван `vcvars64.bat`
    (`cmd /s /c "call ...vcvars64.bat >nul 2>&1 && cl ..."`);
  - w64devkit gcc без libasan/libubsan — линковка с `-fsanitize=address`
    падает, отсюда автооткат на plain.
- Пересборка: `g++.exe check_code.cpp -o check_code.exe -O2` (w64devkit).

## Нативные клиенты (без Python)

- **Win32 (ImGui-стиль)**: `neira-tools/neira_gui.cpp` → `neira_gui.exe`.
  Сборка: `g++ -O2 -std=c++17 -municode neira_gui.cpp -o neira_gui.exe
  -lws2_32 -mwindows`. Запуск — `Neira-gui.bat` (сам поднимает мозг и ждёт health).
- **Qt 6 / QML**: `neira-tools/qt_neira/`:
  - Точка входа `main.cpp` → `qml/Main.qml` (стиль «Basic», контекст `brain`).
  - Бэкенд `neira_brain.h/.cpp`: Winsock + SSE, worker-поток, сессии в
    `neira-tools/sessions/`. **НЕ эмитить токены по одному** — стриминг идёт
    пакетами (порог 384 символов / 24 мс, хвост перед `[DONE]`).
  - Сборка: `build_qt.bat` (moc + g++ MinGW; Qt в `D:\Qt\6.8.2\mingw_64`).
  - Запуск: `Neira-qt.bat` (ставит `PATH`, `QML2_IMPORT_PATH`,
    `QT_QPA_PLATFORM_PLUGIN_PATH`); лог — `qt_neira/neira_qt.log`, не консоль.
  - Правила правок Main.qml: запрет вызовов `positionViewAtEnd`/смены `contentY`
    в `onWidthChanged`/`onHeightChanged`/`onContentHeightChanged`; скролл — только
    через `Qt.callLater`; `userAtBottom` обновляется на `onMovementEnded`,
    автоскролл блокируется при `moving`/`dragging`; в `ColumnLayout`/`RowLayout`
    не смешивать anchors и Layout-свойства.

## Окружение

- Shell — PowerShell (win32): запятая в аргументах ломает разбор (кавычки);
  консоль cp1251 — печатать в файлы, а не в консоль; `curl` = алиас
  `Invoke-WebRequest` (использовать `Invoke-RestMethod`).
- Python: `D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe` (главный),
  `D:\AI\fastqwen\.venv\Scripts\python.exe` (прогрев/вспомогательные).
  **НЕ запускать `uv sync` в Open-LLM-VTuber** — заменит CUDA-торч на CPU из
  `uv.lock`. Запуск голосового приложения — только `uv run --no-sync
  run_server.py`. Свои правила подпроекта: `Open-LLM-VTuber/CLAUDE.md`
  (ruff, pre-commit, архитектура движков).
- Компиляторы: `D:\Programs\w64devkit\bin\gcc.exe` / `g++.exe` (MinGW);
  MSVC: `D:\Programs\VSBuildTools2022\VC\Tools\MSVC\<ver>\bin\Hostx64\x64\cl.exe`
  + `VC\Auxiliary\Build\vcvars64.bat`.
- Обязательные env: `NO_PROXY=localhost,127.0.0.1,::1`,
  `HF_HUB_DISABLE_XET=1`, `PYTHONIOENCODING=utf-8` (и `no_proxy` строчными —
  обе задаются в `.bat`).
- Железо: RTX 3060 Ti 8 ГБ, 32 ГБ RAM. Мозг ~3.2–5 ГБ VRAM, голос
  ~2.5–3.2 ГБ.

## Правила работы (для агентов)

- Правки можно вносить пачками (несколько файлов/мест за ход), но ОБЯЗАТЕЛЬНО
  перед серией правок создавать бэкап `.before-*` для каждого изменяемого файла;
  на одну правку — не больше двух попыток.
- Откаты: копии `.before-*` / `.last-patch` рядом с файлами.
- Модель (GGUF) НИКОГДА не изменяется — файл только читается.
- Удаление файлов — только по правилу автора: список + явное «да», через корзину.

## Автономный запуск (opencode run)

- CLI: `D:\AppData1\ai.opencode.desktop\cli\2.1.4-x64\opencode-cli.exe`;
  обёртка: `D:\AI\opencode-auto.bat "задача"`.
- `--auto` подтверждает разрешения автоматически. Конфиг
  (`~/.config/opencode/opencode.json`) запрещает: `git push`, `Remove-Item`,
  `rm -rf`/`rm -r`, `format`, `Format-Volume`, `Initialize-Disk`,
  `Clear-Disk`, `diskpart`, а также любые вопросы (`question` → deny) —
  не задавать уточняющих вопросов.
- ИСКЛЮЧЕНИЕ для `taskkill`: автор разрешил самостоятельно перезапускать и
  завершать процессы запущенных файлов проекта (занятый exe, старый мозг на
  8080 и т.п.), если они мешают выполнению задачи.
- Модель по умолчанию: `inception/mercury-3`. Опции: `--agent build`,
  `--format json`, `--continue` (продолжить последнюю сессию).
- Встроенного «токенного бюджета» нет — защита от переполнения только
  авто-компактизация (15k токенов).

## Поведение: план до конца

- Многошаговая задача (>~2 действий): сразу запустить
  `opencode-cli run "<полный текст задачи>" --auto` через shell и дождаться
  завершения; вернуться к пользователю только с полным результатом.
- Задачу доводить до конца без участия пользователя: если мешает запущенный
  файл (занятый exe, процесс, порт) — самостоятельно перезапустить/завершить
  его и продолжить работу.
- Внимание пользователя требуется только в трёх случаях:
  1) задача не может быть выполнена качественно (нет данных/доступа/возможности);
  2) необходимо удаление каких-либо файлов (список + явное «да», через корзину);
  3) есть предложение «получше» — рекомендации по улучшению приветствуются,
     их можно привести вместе с результатом, не блокируя завершение.
- Не завершать ход словами «сейчас сделаю/ща/потом» — действие выполняется
  в этом же ходе.
- Ответы оформлять структурированно: таблицы, ✅/❌/⏳, короткие пункты,
  без «стен текста».
