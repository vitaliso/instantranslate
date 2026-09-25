# <img width="32" height="32" alt="instantranslate_icon" src="https://github.com/user-attachments/assets/fb8fcc88-0d9e-4cae-92a7-ad139fba5130" /> Instant Translator


> System-wide instant text translator for Windows. Select text → Ctrl+C → Ctrl+C → translation.

Системная утилита для моментального перевода текста в любой Windows-программе.

<img width="947" height="372" alt="изображение" src="https://github.com/user-attachments/assets/ef14627a-fb79-4340-821d-ff5a8151d546" />


## How it works / Как работает

1. **Select text** in any app (browser, IDE, terminal, PDF, games)  
   **Выделяешь текст** в любой программе
2. **Ctrl+C** (copies to clipboard — как обычно копируешь)  
   **Ctrl+C** → **Ctrl+C** (second press triggers translation / второй раз запускает перевод)
3. Minimal overlay appears with **only the translation** on a yellow-highlight background. Translation is **auto-copied** to clipboard.  
   Появляется минималистичный оверлей **только с переводом** на жёлтом фоне. Перевод **автоматически копируется** в буфер.

The translation keeps the structure of the original: paragraphs, line breaks, indentation-free lines and inline formatting.  
Перевод сохраняет структуру оригинала: абзацы, переносы строк, строки без отступов и инлайн-форматирование.

Overlay stays open while mouse is **stationary**. Move the cursor → overlay closes. Press **Escape** to close immediately.  
Оверлей висит, пока мышь **неподвижна**. Шевельнул курсором → закрывается. **Escape** — закрыть сразу.

**Exit / Выход:** `Ctrl+Shift+Q`

## Features / Возможности

- ✅ **0 dependencies** — pure Python, only standard library / чистый Python, только стандартная библиотека
- ✅ **Works in any app** — browser, IDE, terminal, games, PDF readers / работает в любой программе
- ✅ **Structure preserved** — paragraphs, line breaks, no empty lines, no indents / абзацы, переносы, без пустых строк и отступов
- ✅ **Inline formatting** — `**bold**`, `*italic*`, `` `code` ``, `~~strikethrough~~` / жирный, курсив, код, зачёркнутый
- ✅ **Real formatting** — `<b>` `<i>` `<s>` `<code>` are read from the clipboard's HTML flavor (browser, Word, PDF) / берутся из HTML-версии буфера обмена
- ✅ **Multi-monitor** — overlay positions correctly on any display / корректная позиция на любом мониторе
- ✅ **Auto-copy** — translation is copied to clipboard automatically / перевод сразу в буфере
- ✅ **Single instance** — prevents duplicate launches / защита от дублирования
- ✅ **Minimal UI** — transparent overlay with auto-close / минималистичный интерфейс с авто-закрытием

## Structure & formatting / Структура и формат

The source is normalized before translation and the result is realigned to it, so the translation mirrors the original layout.  
Исходник нормализуется перед переводом, а результат выравнивается обратно — перевод повторяет вёрстку оригинала.

| Rule | What it does |
|---|---|
| Paragraphs & line breaks | Every non-empty source line = one translation line, in the same order |
| No empty lines | Blank lines are dropped — the text stays dense, nothing is padded |
| No indentation | Leading spaces/tabs are removed, runs of spaces collapse to one |
| Real formatting | `<b>` `<i>` `<s>` `<code>` read from the clipboard's HTML flavor and re-applied to the translation |
| Inline markup | `**bold**`, `*italic*`, `` `code` ``, `~~strikethrough~~` also work when typed in the source text |

### Where the formatting comes from / Откуда берётся форматирование

The clipboard usually holds **two** things: plain text and an HTML version of the same selection. The plain text has no
formatting in it — the bold lives only in the HTML. The app reads the HTML flavor (`CF_HTML` via Win32), converts
`<b> <strong> <i> <em> <s> <del> <code>` into markers, and Google carries those markers into the translation.

Приложение читает HTML-версию выделения из буфера и превращает `<b>/<i>/<s>/<code>` в маркеры, которые Google переносит в перевод.

| Copy from | Formatting detected? |
|---|---|
| Browser, Word, PDF reader, most desktop apps | ✅ yes — HTML flavor is present |
| IDE, terminal, plain notepad | ❌ no — those apps only put plain text on the clipboard, there is nothing to read |
| Chat with Markdown | ✳️ only if the app copies the literal `**`/`*`/`` ` `` characters |

If the HTML brings more text than the plain text (a whole page instead of a fragment), the app falls back to plain text.
Если HTML притащил лишнее (страницу вместо фрагмента), приложение откатывается к обычному тексту.

Google Translate preserves newlines, so the alignment is normally a no-op. If the API returns a different number of lines, the translation is redistributed proportionally and split at sentence boundaries to match the original.  
Google сохраняет переносы, поэтому выравнивание обычно ничего не меняет. Если строк всё же не столько же, перевод распределяется пропорционально и режется по границам предложений.

Markup is only recognized when the delimiters are tight (`**bold**`, not `** bold **`), so `a * b * c` and `2*3*4` stay literal.  
Разметка распознаётся только при «плотных» маркерах, поэтому `a * b * c` и `2*3*4` остаются обычным текстом.


## Language support / Поддерживаемые языки

Only **Russian ↔ English** (ru ↔ en). Other languages are rejected with a message.  
Только **русский ↔ английский**. Другие языки не поддерживаются.

This is intentional — the utility is designed for fast bidirectional translation between two specific languages.  
Это осознанное ограничение — утилита для быстрого двунаправленного перевода между двумя конкретными языками.

## Requirements / Требования

- **Windows** (uses `GetAsyncKeyState` / `CreateMutexW` — Win32 API)
- **Python 3.x** (tested on 3.10+)
- **Internet connection** (Google Translate API)
- Nothing else — **zero dependencies**

## Installation / Установка

```bash
git clone https://github.com/vitaliso/instantranslate.git
cd instantranslate
python instant_translator.py
```

Or just download the files — no `pip install` needed.

## Launch methods / Способы запуска

| Method | What it does |
|---|---|
| `python instant_translator.py` | Runs with a console window (visible) |
| `pythonw instant_translator.py` | Runs silently, no console (recommended) |
| `run_hidden.vbs` | Launches silently via `pythonw` — double-click friendly |
| `run.bat` | Launches minimized via `pythonw` |

## Autorun / Автозагрузка

**Easy way (recommended):** Double-click `install_startup.vbs` in the project folder — it creates the correct startup shortcut automatically.  
**Простой способ:** дважды кликни `install_startup.vbs` — он сам создаст ярлык в автозагрузке.

Manual way: Run `shell:startup` (Win+R), create a shortcut to:
```
pythonw.exe "F:\путь\к\instant_translator.py"
```
Start in: the project folder.

Or create a task in Task Scheduler for more control.

## Configuration / Настройка

Edit the constants at the top of `instant_translator.py`:

| Constant | Default | Description |
|---|---|---|
| `DOUBLE_PRESS_MS` | `500` | Max interval between two Ctrl+C presses (ms) |
| `POLL_INTERVAL` | `0.025` | Keyboard polling interval (seconds) |
| `OVERLAY_MAX_CHARS` | `3000` | Max text length for translation |
| `OVERLAY_MAX_WIDTH_CHARS` | `60` | Max overlay width in characters (wraps long text) |
| `OVERLAY_ALPHA` | `0.94` | Window opacity (1.0 = opaque, 0.94 = 6% transparent) |
| `BG_COLOR` | `#FFFFF5` | Window background color |
| `TEXT_COLOR` | `#333333` | Text color |
| `HL_COLOR` | `#FFFFE0` | Translation highlight / marker color |
| `ERROR_BG` | `#FFF0F0` | Error overlay background |
| `ERROR_FG` | `#CC3333` | Error overlay text color |
| `OVERLAY_FONT` | `Segoe UI` | Overlay font family |
| `OVERLAY_SIZE` | `12` | Overlay font size |
| `CODE_FONT` | `Consolas` | Font used for `` `code` `` spans |

## Files

| File | Purpose |
|---|---|
| `instant_translator.py` | Main script — all logic |
| `run_hidden.vbs` | Silent VBS launcher (no console) |
| `run.bat` | Batch launcher (minimized console) |
| `install_startup.vbs` | One-click autorun installer — run once |
| `README.md` | This file |
| `LICENSE` | MIT License |

## Technical details / Технические детали

- **Hotkey detection:** Polls `GetAsyncKeyState` every 25ms — no global hooks or admin required
- **Translation:** Google Translate API (unofficial endpoint) — `translate.googleapis.com/translate_a/single`
- **Clipboard:** Win32 `CF_HTML` (registered format `HTML Format`) for formatting + `CF_UNICODETEXT` fallback; falls back to plain text if the HTML is missing or pulls in extra text
- **Text pipeline:** `normalize_text` (no indents, no blank lines, no double spaces) → single request with `\n` → `align_structure` (realigns line count to the source)
- **Rendering:** Tkinter rows of `Label` widgets — one per styled segment, so `**bold**` / `` `code` `` render with real fonts; lines are pre-wrapped by pixel width, the overlay hugs the text
- **Overlay:** Tkinter `Toplevel` — borderless, always-on-top, alpha-blended
- **Single instance:** `CreateMutexW` with named mutex `Local\InstantTranslator_Mutex`
- **Multi-monitor:** `GetSystemMetrics(SM_XVIRTUALSCREEN…SM_CYVIRTUALSCREEN)` for virtual desktop bounds

## License

MIT
