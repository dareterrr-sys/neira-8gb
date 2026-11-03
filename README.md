# Нейра — локальный ИИ-компаньон на видеокарте 8 ГБ

> 🚧 **Исследовательский проект в разработке.** Код написан под одну конкретную машину (пути `D:\AI\…` прописаны жёстко), многое не доделано и не вычищено. Это журнал работы, а не готовый продукт.

*[English below](#english)*

Нейра — ИИ-компаньон, который целиком живёт на домашнем ПК (RTX 3060 Ti 8 ГБ, Ryzen 5 5600X, 32 ГБ RAM), без облака: свой мозг (Qwen3.6-35B-A3B), свой голос, память о собеседнике и «органы» — точный код там, где языковая модель ошибается.

Главный принцип проекта: **один шаг — одно изменение — один замер**. Каждое решение, включая неудачные, записано в [журнале](journal/00%20Журнал%20Нейры.md).

## Что здесь интересного

| Направление | Что сделано | Замер |
|---|---|---|
| **Горячие эксперты MoE** | Своя правка llama.cpp: самые используемые эксперты (по карте экспертов) один раз копируются в VRAM и считаются там, остальные — на CPU; пул размеряется по реально свободной VRAM | генерация 32 → 42.7 ток/с, чтение промпта 285 → 580 ток/с на 8 ГБ |
| **Датчик сомнения** | Линейный зонд на скрытом состоянии (слой 16) предсказывает, знает ли модель ответ; встроен в сервер | AUC 0.955–0.986 на фактах |
| **Вектор «не знаю»** | Управляющий вектор отказа, включаемый только на вопросах эрудиции | уверенная ложь о незнакомых людях 65 → 26 из 80, вместе с датчиком — до 2; задачи не тронуты |
| **Совет ролей v4** | Три специалиста из того же мозга; спор решает «мыслитель»; числовой итог — слепые проверки | MGSM-ru ≈ 95% после разбора ошибок |
| **Органы** | Калькулятор, календарь, буквы, слова, единицы, словари русского языка — код вместо токенов | органы слов и единиц: 27 → 47 из 60 |
| **Голос** | Fine-tune Qwen3-TTS (LoRA) + int8 со своим Triton-ядром, «парковка» голоса в RAM за 0.1 с | голос 4.9 → 2.5 ГБ VRAM |

Подробный рассказ — [docs/article_ru.md](docs/article_ru.md) (черновик).

## Устройство

```
src/
  brain/        конфиги мозга, патч llama.cpp (горячие эксперты, датчик, cvec), пул экспертов, веса датчика
  expert-map/   построение пула экспертов и карты по корпусу
  agent/        диспетчер реплик (правки Open-LLM-VTuber): органы, совет, память, обмен VRAM с голосом
  council/      совет ролей, маршрутизатор, оценка на наборах вопросов
  organs/       органы на C/C++/Python (bukvy, slova, edinicy, russkiy, perception, calendar…)
  chat/         текстовый чат, правила поведения, память фактов, орган проверки кода check_code
  clients/      нативные клиенты: C++ CLI, Win32 GUI, Qt/QML
  voice/        сервер голоса (Qwen3-TTS, int8, судьи качества)
  knowledge/    скрипты библиотеки русского языка и OCR
  start/        запуск всего вместе
journal/        журнал исследований по темам (Obsidian)
docs/           статья, разбор ошибок совета
```

## Чего здесь нет — и почему

- **Весов моделей и голоса.** Голос дообучен на чужих записях, поэтому публикуется только метод, без весов и данных.
- **Банков заданий ЕГЭ, справочных текстов (Розенталь, Ожегов) и списков ФИПИ** — это чужие материалы.
- Используются: [llama.cpp](https://github.com/ggml-org/llama.cpp), [Qwen3.6](https://huggingface.co/Qwen), [Qwen3-TTS](https://github.com/QwenLM), [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber), RUPunct, RUAccent, OpenCorpora, Hunspell — у каждого своя лицензия.

## Контакты

Вопросы, идеи и найденные баги — во вкладку **Issues** этого репозитория. Автор — [Filldas](https://github.com/dareterrr-sys).

## Лицензия

Собственный код проекта — **AGPL-3.0** (см. [LICENSE](LICENSE)): пользоваться и изменять можно, но тот, кто встроит этот код в свой продукт или сервис, обязан открыть и свой код на тех же условиях.

---

## English

**Neira** is a fully local AI companion running on a home PC with an **8 GB GPU** (RTX 3060 Ti): a 35B MoE brain (Qwen3.6-35B-A3B), a fine-tuned voice, long-term memory and deterministic "organs" for the tasks language models get wrong. 🚧 *Work in progress, written for one specific machine.*

Highlights:
- **Hot MoE experts** — a llama.cpp patch keeps the most used experts (by an expert-usage map) in VRAM and computes the rest on the CPU: generation 32 → 42.7 tok/s, prompt reading 285 → 580 tok/s on 8 GB.
- **Doubt sensor** — a linear probe on layer-16 hidden states predicts whether the model knows the answer (AUC 0.955–0.986 on facts), built into the server.
- **"I don't know" steering vector**, applied only to factual-recall questions: confident lies about unknown people 65 → 26 of 80 (→ 2 with the sensor), reasoning untouched.
- **Council of roles** from the same model with a "thinker" for disputes and blind numeric checks.
- **Organs** — code instead of tokens: calculator, calendar, letters, words, units, Russian-language dictionaries.
- **Voice** — Qwen3-TTS LoRA fine-tune, int8 with a custom Triton kernel (4.9 → 2.5 GB VRAM), parked in RAM in 0.1 s when the brain needs the GPU.

The research journal (Russian) is in [`journal/`](journal/). Model weights, voice data and third-party datasets are not included. Own code is licensed under **AGPL-3.0**. Questions and bug reports: **Issues**; author — [Filldas](https://github.com/dareterrr-sys).
