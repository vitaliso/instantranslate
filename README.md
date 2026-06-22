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

Overlay stays open while mouse is **stationary**. Move the cursor → overlay closes. Press **Escape** to close immediately.  
Оверлей висит, пока мышь **неподвижна**. Шевельнул курсором → закрывается. **Escape** — закрыть сразу.

**Exit / Выход:** `Ctrl+Shift+Q`

## Features / Возможности

- ✅ **0 dependencies** — pure Python, only standard library / чистый Python, только стандартная библиотека
- ✅ **Works in any app** — browser, IDE, terminal, games, PDF readers / работает в любой программе
- ✅ **Multi-monitor** — overlay positions correctly on any display / корректная позиция на любом мониторе
- ✅ **Auto-copy** — translation is copied to clipboard automatically / перевод сразу в буфере
- ✅ **Single instance** — prevents duplicate launches / защита от дублирования
- ✅ **Minimal UI** — transparent overlay with auto-close / минималистичный интерфейс с авто-закрытием

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
- **Overlay:** Tkinter `Toplevel` — borderless, always-on-top, alpha-blended
- **Single instance:** `CreateMutexW` with named mutex `Local\InstantTranslator_Mutex`
- **Multi-monitor:** `GetSystemMetrics(SM_XVIRTUALSCREEN…SM_CYVIRTUALSCREEN)` for virtual desktop bounds

## License

MIT
