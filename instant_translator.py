#!/usr/bin/env python3
"""
Instant Translator — system-wide translation utility.
Выдели текст → Ctrl+C (копирует) → Ctrl+C (переводит) → оверлей с переводом.

Чистый Python, zero external dependencies.
Работает в любой программе: браузер, IDE, терминал, игры, PDF-ридеры.
"""

import bisect
import ctypes
import json
import re
import sys
import threading
import time
import tkinter as tk
from html.parser import HTMLParser
from tkinter import font as tkfont
from pathlib import Path
import urllib.parse
import urllib.request

# ─── Configuration ───────────────────────────────────────────────────────────
DOUBLE_PRESS_MS = 500           # Окно для двойного нажатия Ctrl+C (мс)
POLL_INTERVAL = 0.025           # 25ms — частота опроса клавиш
OVERLAY_MAX_CHARS = 3000        # Макс. длина текста для перевода
OVERLAY_MAX_WIDTH_CHARS = 60   # Макс. ширина оверлея в символах (перенос строки)
OVERLAY_ALPHA = 0.94            # 6% прозрачности
BG_COLOR = "#FFFFF5"            # фон окна (максимально нейтральный, почти невидим при alpha)
TEXT_COLOR = "#333333"
HL_COLOR = "#FFFFE0"            # цвет «выделения» перевода (жёлтый маркер)
ERROR_BG = "#FFF0F0"
ERROR_FG = "#CC3333"
OVERLAY_FONT = "Segoe UI"       # основной шрифт оверлея
OVERLAY_SIZE = 12               # кегль оверлея
CODE_FONT = "Consolas"          # шрифт для `код`


# ─── Инлайн-разметка: **жирный** *курсив* `код` ~~зачёркнутый~~ ***оба*** ─────
# Маркер → (стиль, ширина маркера). Порядок важен: "***" проверяется раньше "**".
MARKUP_STYLES: dict[str, tuple[str, int]] = {
    "***": ("bi", 3),
    "**": ("b", 2),
    "*": ("i", 1),
    "~~": ("s", 2),
    "`": ("c", 1),
}

MARKER_CHARS = {"b": "**", "i": "*", "bi": "***", "s": "~~", "c": "`"}

# Внутренние пробелы запрещены — иначе «a * b * c» превратится в курсив.
# Границы разрешают соседние маркеры: «**жирный***курсив*» из двух подряд идущих стилей.
MARKUP_RE = re.compile(
    r"(?<!\w)("
    r"\*\*\*(?!\s)[^\n]+?(?<!\s)\*\*\*"
    r"|\*\*(?!\s)[^\n]+?(?<!\s)\*\*"
    r"|\*(?!\s)[^*\n]+?(?<!\s)\*"
    r"|~~(?!\s)[^\n]+?(?<!\s)~~"
    r"|`[^`\n]+?`"
    r")(?!\w)"
)


def split_markup(line: str) -> list[tuple[str, str]]:
    """Делит строку на пары (текст, стиль) по инлайн-разметке."""
    out: list[tuple[str, str]] = []
    pos = 0
    for match in MARKUP_RE.finditer(line):
        token = match.group(0)
        style, width = next(
            (s, w) for marker, (s, w) in MARKUP_STYLES.items() if token.startswith(marker)
        )
        if match.start() > pos:
            out.append((line[pos:match.start()], ""))
        out.append((token[width:-width], style))
        pos = match.end()
    if pos < len(line):
        out.append((line[pos:], ""))
    return out


def break_token(token: str, style: str, limit: int, measure) -> list[str]:
    """Режет неразрывный кусок (URL, хеш, base64) на части по ширине limit."""
    per_char = max(1, measure("0" * 10, style) // 10)
    size = max(1, limit // per_char)
    return [token[i:i + size] for i in range(0, len(token), size)]


def _flush(row: list[tuple[str, str]], rows: list[list[tuple[str, str]]]) -> None:
    """Закрывает строку переноса: убирает хвостовые пробелы, склеивает сегменты одного стиля."""
    items = list(row)
    if items:
        text, style = items[-1]
        text = text.rstrip()
        if text:
            items[-1] = (text, style)
        else:
            items.pop()
    merged: list[tuple[str, str]] = []
    for text, style in items:
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    rows.append(merged)


def wrap_line(line: str, limit: int, measure) -> list[list[tuple[str, str]]]:
    """
    Переносит строку по ширине limit px. → список строк, каждая = список (текст, стиль).
    Стиль переживает перенос: жирный текст остаётся жирным в обеих строках.
    """
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    width = 0

    for text, style in split_markup(line):
        for token in re.split(r"(\s+)", text):
            if not token:
                continue
            if not token.strip():                     # пробел — только в конце строки
                if row:
                    row.append((token, style))
                    width += measure(token, style)
                continue
            token_width = measure(token, style)
            if row and width + token_width > limit:   # перенос
                _flush(row, rows)
                row, width = [], 0
                token = token.lstrip()
                if not token:
                    continue
                token_width = measure(token, style)
            if not row and token_width > limit:       # неразрывный кусок длиннее строки
                rows.extend((piece, style)
                            for piece in break_token(token, style, limit, measure))
                continue
            row.append((token, style))
            width += token_width

    if row:
        _flush(row, rows)
    return rows or [[]]


# ─── Структура текста ────────────────────────────────────────────────────────

def normalize_text(raw: str, max_chars: int = OVERLAY_MAX_CHARS) -> list[str]:
    """
    Приводит текст к плотным строкам: без пустых, без отступов, без дублей пробелов.
    Абзацы и переносы становятся одинаковыми — каждый на своей строке.
    """
    lines: list[str] = []
    for chunk in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", chunk).strip()
        if line:
            lines.append(line)
    return clip_text(lines, max_chars)


def clip_text(lines: list[str], max_chars: int) -> list[str]:
    """Обрезает по лимиту символов, не разрывая строки (кроме первой)."""
    out: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + (1 if out else 0)
        if used + cost > max_chars:
            room = max_chars - used - (1 if out else 0)
            if not out and room > 0:
                out.append(line[:room])
            break
        out.append(line)
        used += cost
    return out


def _bucket_by_length(src: list[str], tgt: list[str]) -> list[list[str]]:
    """Раскладывает строки перевода по строкам оригинала пропорционально длине."""
    bounds: list[int] = []
    acc = 0
    for line in src:
        acc += len(line)
        bounds.append(acc)
    scale = (bounds[-1] or 1) / max(1, sum(len(t) for t in tgt))

    buckets: list[list[str]] = [[] for _ in src]
    acc = 0
    for line in tgt:
        index = bisect.bisect_right(bounds, (acc + len(line) / 2) * scale) - 1
        buckets[min(max(index, 0), len(src) - 1)].append(line)
        acc += len(line)
    return buckets


def _fill_empty(buckets: list[list[str]]) -> None:
    """Ни одна строка перевода не должна остаться пустой."""
    for i in range(len(buckets)):
        if buckets[i]:
            continue
        nxt = i + 1
        while nxt < len(buckets) and not buckets[nxt]:
            nxt += 1
        if nxt < len(buckets):
            buckets[i] = [buckets[nxt].pop(0)]
        elif i and len(buckets[i - 1]) > 1:
            buckets[i] = [buckets[i - 1].pop()]


def _split_point(text: str) -> tuple[str, str]:
    """Делит строку пополам по границе предложения, иначе — по пробелу."""
    if len(text) < 4:
        return "", ""
    middle = len(text) // 2
    for pattern in (r"[.!?…]+[\"'»]?\s", r"\s"):
        hits = [m.end() for m in re.finditer(pattern, text)]
        if hits:
            point = min(hits, key=lambda p: abs(p - middle))
            head, tail = text[:point].strip(), text[point:].strip()
            if head and tail:
                return head, tail
    if len(text) < 20:                       # короткое слово лучше не рубить
        return "", ""
    return text[:middle].strip(), text[middle:].strip()


def _split_until(buckets: list[list[str]], target: int) -> None:
    """Добирает количество строк до target, разбивая самые длинные."""
    while sum(1 for b in buckets if b) < target:
        candidates = sorted(
            (i for i, b in enumerate(buckets) if len(b) == 1 and len(b[0]) > 1),
            key=lambda i: -len(buckets[i][0]),
        )
        for index in candidates:
            head, tail = _split_point(buckets[index][0])
            if head and tail:
                buckets[index] = [head]
                buckets.insert(index + 1, [tail])
                break
        else:
            break                       # дальше делить нечего


def align_structure(src: list[str], translated: str) -> list[str]:
    """
    Приводит перевод к структуре оригинала: столько же строк, в том же порядке.
    Google переносы строк обычно сохраняет — выравнивание нужно как страховка.
    """
    tgt = normalize_text(translated, max_chars=10 ** 6)
    if not src:
        return []
    if not tgt:
        return list(src)
    if len(tgt) == len(src):
        return tgt

    buckets = _bucket_by_length(src, tgt)
    _fill_empty(buckets)
    _split_until(buckets, len(src))
    return [" ".join(bucket).strip() for bucket in buckets if bucket]


# ─── Форматирование из буфера обмена (CF_HTML) ───────────────────────────────
# В буфере лежит не только plain text, но и HTML-версия выделения — там есть
# реальные <b>/<i>/<s>/<code>. Из неё собираем маркеры, которые Google переносит
# в перевод, а оверлей уже умеет рисовать.

CF_HTML_NAME = "HTML Format"       # CF_HTML — зарегистрированный, а не стандартный формат
MAX_HTML_BYTES = 8 * 1024 * 1024


def open_clipboard(tries: int = 3) -> bool:
    """Открывает буфер обмена. Нужно для GetClipboardData — он требует открытого буфера."""
    for _ in range(tries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def read_clipboard_html() -> str | None:
    """Читает HTML-версию буфера обмена через Win32 (CF_HTML). None — если её нет."""
    try:
        fmt = user32.RegisterClipboardFormatW(CF_HTML_NAME)
        if not fmt or not open_clipboard():
            return None
        try:
            handle = user32.GetClipboardData(fmt)
            if not handle:
                return None
            lock = kernel32.GlobalLock(handle)
            if not lock:
                return None
            try:
                head = ctypes.string_at(lock, 1024)
                start = _header_offset(head, "StartHTML")
                end = _header_offset(head, "EndHTML")
                if start is not None and end is not None and end > start:
                    raw = ctypes.string_at(lock + start, min(end - start, MAX_HTML_BYTES))
                else:
                    raw = ctypes.string_at(lock, min(kernel32.GlobalSize(handle),
                                                     MAX_HTML_BYTES))
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None

    raw = raw.split(b"\x00")[0]
    if b"<" not in raw[:400]:                     # это не HTML (например, обычный текст)
        return None
    html = _decode_html(raw)
    return html[html.index("<"):] if "<" in html else None


def _header_offset(head: bytes, name: str) -> int | None:
    """Читает StartHTML:/EndHTML:/StartFragment: из заголовка CF_HTML."""
    match = re.search(name.encode() + rb":\s*(\d+)", head)
    return int(match.group(1)) if match else None


def _decode_html(raw: bytes) -> str:
    """CF_HTML обычно UTF-8, но Windows-приложения часто пишут windows-1251."""
    match = re.search(rb"charset=([\w-]+)", raw[:400], re.IGNORECASE)
    encodings = []
    if match:
        try:
            encodings.append(match.group(1).decode("ascii"))
        except UnicodeDecodeError:
            pass
    encodings += ["utf-8", "cp1251", "latin-1"]
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("latin-1", "replace")


def _style_key(bits: frozenset[str]) -> str:
    """Набор стилей → один стиль сегмента (приоритет: код > зачёркнутый > жирный/курсив)."""
    if not bits:
        return ""
    if "c" in bits:
        return "c"
    if "s" in bits:
        return "s"
    if "b" in bits and "i" in bits:
        return "bi"
    if "b" in bits:
        return "b"
    if "i" in bits:
        return "i"
    return ""


class _StyleParser(HTMLParser):
    """Вытаскивает из HTML текст с пометками стилей: <b> <i> <s> <code>."""

    SKIP = {"script", "style", "head", "title", "meta", "link", "noscript",
            "svg", "iframe", "canvas", "video", "audio", "template", "input", "button"}
    BLOCK = {"p", "div", "br", "li", "tr", "td", "th", "ul", "ol", "table", "tbody",
             "thead", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
             "header", "footer", "nav", "aside", "blockquote", "pre", "figure",
             "figcaption", "hr", "form", "dl", "dt", "dd", "main", "body", "html"}
    STYLES = {
        "b": "b", "strong": "b", "h1": "b", "h2": "b", "h3": "b",
        "h4": "b", "h5": "b", "h6": "b", "th": "b",
        "i": "i", "em": "i", "cite": "i", "var": "i", "dfn": "i", "address": "i",
        "s": "s", "strike": "s", "del": "s",
        "code": "c", "kbd": "c", "samp": "c", "tt": "c", "pre": "c",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, str]] = []
        self._stack: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in self.BLOCK:
            self._emit("\n")
        if tag in self.STYLES:
            self._stack.append(self.STYLES[tag])

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self._emit("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in self.STYLES and self._stack:
            self._stack.pop()
        if tag in self.BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self._emit(data)

    def _emit(self, text: str) -> None:
        if text:
            self.parts.append((text, _style_key(frozenset(self._stack))))


def html_to_segments(html: str) -> list[tuple[str, str]]:
    """HTML → список (текст, стиль) с объединением соседних кусков одного стиля."""
    body = html
    start = body.find("<!--StartFragment-->")
    end = body.rfind("<!--EndFragment-->")
    if start != -1 and end > start:
        body = body[start + len("<!--StartFragment-->"):end]

    parser = _StyleParser()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        return []

    merged: list[tuple[str, str]] = []
    for text, style in parser.parts:
        if not text:
            continue
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def insert_style_markers(parts: list[tuple[str, str]]) -> str:
    """Расставляет **жирный** / *курсив* / `код` / ~~зачёркнутый~~ по реальному форматированию."""
    out: list[str] = []
    for text, style in parts:
        if not style:
            out.append(text)
            continue
        marker = MARKER_CHARS[style]
        chunks: list[str] = []
        for index, part in enumerate(text.split("\n")):
            if index:
                chunks.append("\n")
            stripped = part.strip()
            if not stripped:
                chunks.append(part)               # пробелы без маркеров
                continue
            lead = part[:len(part) - len(part.lstrip())]
            trail = part[len(part.rstrip()):]
            chunks.append(f"{lead}{marker}{stripped}{marker}{trail}")
        out.append("".join(chunks))
    return "".join(out)


# ─── Windows API ─────────────────────────────────────────────────────────────
VK_CONTROL = 0x11
VK_C = 0x43
KEY_PRESSED = 0x8000

# System metrics для multi-monitor
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64-битные указатели нельзя оставлять как c_int — иначе дескрипторы обрезаются
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.RegisterClipboardFormatW.restype = ctypes.c_uint
user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_int
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]


class InstantTranslator:
    """Основной класс — горячая клавиша + перевод + оверлей."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("InstantTranslator")

        # иконка приложения
        icon_path = Path(__file__).parent / "instantranslate_icon_256.png"
        if icon_path.is_file():
            icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, icon)
            self._app_icon = icon  # keep ref to prevent GC

        self._fonts = {
            "": tkfont.Font(family=OVERLAY_FONT, size=OVERLAY_SIZE),
            "b": tkfont.Font(family=OVERLAY_FONT, size=OVERLAY_SIZE, weight="bold"),
            "i": tkfont.Font(family=OVERLAY_FONT, size=OVERLAY_SIZE, slant="italic"),
            "bi": tkfont.Font(family=OVERLAY_FONT, size=OVERLAY_SIZE,
                              weight="bold", slant="italic"),
            "s": tkfont.Font(family=OVERLAY_FONT, size=OVERLAY_SIZE),
            "c": tkfont.Font(family=CODE_FONT, size=OVERLAY_SIZE),
        }

        self.last_press_time: float = 0.0
        self.prev_c_down: bool = False
        self.running = True
        self.overlay: tk.Toplevel | None = None
        self.overlay_active: bool = False
        self._mouse_idle_pos: tuple[int, int] | None = None
        self._mouse_monitor_id: str | None = None

        # поток опроса клавиш
        self.monitor = threading.Thread(target=self._poll_keys, daemon=True)
        self.monitor.start()

    # ── Keyboard poll ────────────────────────────────────────────────────────

    def _poll_keys(self) -> None:
        """Проверяет состояние Ctrl+C каждые POLL_INTERVAL мс."""
        while self.running:
            try:
                ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & KEY_PRESSED)
                ckey = bool(user32.GetAsyncKeyState(VK_C) & KEY_PRESSED)
                c_down = ctrl and ckey

                if c_down and not self.prev_c_down:
                    now = time.time()
                    delta = (now - self.last_press_time) * 1000
                    if self.last_press_time > 0 and delta < DOUBLE_PRESS_MS:
                        self.root.after(10, self._on_double_press)
                        self.last_press_time = 0.0
                    else:
                        self.last_press_time = now

                self.prev_c_down = c_down
                time.sleep(POLL_INTERVAL)
            except Exception:
                time.sleep(POLL_INTERVAL)

    # ── Double-press handler ─────────────────────────────────────────────────

    def _on_double_press(self) -> None:
        """Срабатывает на второе Ctrl+C: читает буфер и показывает перевод."""
        if self.overlay_active:
            return

        text = self._get_clipboard_text()
        if not text:
            return
        # структура исходника: строки без отступов, без пустых, без дублей пробелов
        lines = normalize_text(text)
        if not lines:
            return

        self._show_loading()

        thread = threading.Thread(
            target=self._do_translate,
            args=(lines,),
            daemon=True,
        )
        thread.start()

    def _get_clipboard_text(self) -> str | None:
        """
        Текст для перевода. Если в буфере есть HTML-версия выделения — берём её
        и расставляем маркеры по реальному форматированию (**жирный**, *курсив*…).
        """
        styled = self._styled_clipboard_text()
        if styled:
            return styled
        return self._plain_clipboard_text()

    def _plain_clipboard_text(self) -> str | None:
        """Безопасно читает текст из буфера обмена (3 попытки)."""
        for _ in range(3):
            try:
                return self.root.clipboard_get()
            except tk.TclError:
                time.sleep(0.05)
        return None

    def _styled_clipboard_text(self) -> str | None:
        """Форматирование из CF_HTML. None — если HTML нет или он ничего не добавляет."""
        html = read_clipboard_html()
        if not html:
            return None
        parts = html_to_segments(html)
        if not any(style for _, style in parts):
            return None
        text = insert_style_markers(parts)
        if not text.strip():
            return None
        plain = self._plain_clipboard_text()
        if plain and len(text) > len(plain) * 2 + 40:
            return None                      # HTML притащил лишнее (страница, а не фрагмент)
        return text

    # ── Translation ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_google_response(data: list) -> str:
        """Извлекает текст перевода из ответа Google Translate API."""
        parts = []
        for block in data[0]:
            if isinstance(block, list) and len(block) > 0 and block[0]:
                parts.append(block[0])
        return "".join(parts)

    def _google_translate(self, text: str, target: str, source: str = "auto") -> tuple[str, str]:
        """Делает запрос к Google Translate. Возвращает (перевод, обнаруженный_язык)."""
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={source}&tl={target}&dt=t&q="
            + urllib.parse.quote(text, safe="")
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = self._parse_google_response(data)
        detected = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
        return result, detected

    def _do_translate(self, lines: list[str]) -> None:
        """
        Переводит текст. Поддерживает только ru ↔ en.
        1) Определяет язык через авто-запрос
        2) Если ru → переводит на en, если en → переводит на ru
        3) Остальные языки → ошибка
        """
        SUPPORTED = {"ru", "en"}
        try:
            # Переносы строк Google сохраняет, структура оригинала не теряется
            text = "\n".join(lines)

            # Шаг 1: определяем язык (запрашиваем перевод на ru)
            result, detected = self._google_translate(text, "ru")

            if detected not in SUPPORTED:
                self.root.after(0, self._show_error,
                    f"Только EN ↔ RU. Обнаружено: {detected.upper() or '?'}")
                return

            if detected == "ru":
                # русский → переводим на английский
                result, _ = self._google_translate(text, "en", source="ru")

            # detected == "en" → уже перевели на русский (шаг 1)
            structured = "\n".join(align_structure(lines, result))
            self.root.after(0, self._show_overlay, structured)
        except Exception as exc:
            self.root.after(0, self._show_error, f"Ошибка перевода: {exc}")

    # ── Overlay: общие методы ────────────────────────────────────────────────

    def _create_overlay_window(self) -> tk.Toplevel:
        """Создаёт пустой оверлей."""
        self._close_overlay()
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", OVERLAY_ALPHA)
        overlay.configure(bg=BG_COLOR)
        overlay.bind("<Escape>", lambda e: self._close_overlay())

        self.overlay = overlay
        self.overlay_active = True
        return overlay

    def _position_above_cursor(self) -> None:
        """Размещает оверлей НАД курсором на ЛЮБОМ мониторе (virtual desktop)."""
        self.overlay.update_idletasks()
        cx, cy = self.root.winfo_pointerxy()
        w = self.overlay.winfo_reqwidth()
        h = self.overlay.winfo_reqheight()

        # границы виртуального рабочего стола (все мониторы)
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        # центрируем по X, пытаемся поставить над курсором
        x = max(min(cx - w // 2, vx + vw - w - 4), vx + 4)
        y = cy - h - 8

        if y < vy + 4:                     # сверху не влезает
            y = cy + 18                     # ставим снизу
        if y + h > vy + vh - 4:            # всё равно улетает за край
            y = max(vy + 4, cy - h - 8)     # фиксим

        self.overlay.geometry(f"+{int(x)}+{int(y)}")

    def _start_mouse_monitor(self) -> None:
        """Проверяет позицию мыши каждые 200мс. Если курсор сдвинулся — закрывает оверлей."""
        if not self.overlay_active or not self.overlay:
            self._mouse_idle_pos = None
            self._mouse_monitor_id = None
            return
        try:
            mx = self.overlay.winfo_pointerx()
            my = self.overlay.winfo_pointery()
            if self._mouse_idle_pos is None:
                self._mouse_idle_pos = (mx, my)
            else:
                prev_x, prev_y = self._mouse_idle_pos
                if abs(mx - prev_x) > 3 or abs(my - prev_y) > 3:
                    self._close_overlay()
                    return
            self._mouse_monitor_id = self.overlay.after(200, self._start_mouse_monitor)
        except tk.TclError:
            self._mouse_idle_pos = None
            self._mouse_monitor_id = None

    def _close_overlay(self, _event=None) -> None:
        """Закрывает оверлей и сбрасывает флаги."""
        if self.overlay:
            try:
                if self._mouse_monitor_id:
                    self.overlay.after_cancel(self._mouse_monitor_id)
                self.overlay.destroy()
            except tk.TclError:
                pass
            self.overlay = None
            self.overlay_active = False
            self._mouse_idle_pos = None
            self._mouse_monitor_id = None

    # ── Overlay: отрисовка ───────────────────────────────────────────────────

    def _measure(self, text: str, style: str) -> int:
        """Ширина текста в пикселях для указанного стиля."""
        return self._fonts[style].measure(text)

    def _render(self, parent: tk.Misc, text: str, bg: str, fg: str) -> tk.Frame:
        """
        Строит перевод в виде строк Labels — так работает разное форматирование
        (**жирный**, *курсив*, `код`, ~~зачёркнутый~~) внутри одной строки.
        """
        limit = self._measure("0" * OVERLAY_MAX_WIDTH_CHARS, "")
        container = tk.Frame(parent, bg=bg)
        for line in text.split("\n"):
            for row in wrap_line(line, limit, self._measure):
                self._render_row(container, row, bg, fg)
        container.pack(anchor="w")
        return container

    def _render_row(self, parent: tk.Misc, segments: list[tuple[str, str]],
                    bg: str, fg: str) -> None:
        """Одна отображаемая строка: сегменты разных стилей рядом."""
        frame = tk.Frame(parent, bg=bg)
        for text, style in segments:
            self._render_segment(frame, text, style, bg, fg)
        frame.pack(anchor="w")

    def _render_segment(self, parent: tk.Misc, text: str, style: str,
                        bg: str, fg: str) -> None:
        """Сегмент строки. Для зачёркнутого — Label + нарисованная черта."""
        font = self._fonts[style]
        if style != "s":
            tk.Label(parent, text=text, font=font, bg=bg, fg=fg,
                     padx=0, pady=0, anchor="w").pack(side="left")
            return

        holder = tk.Frame(parent, bg=bg)
        tk.Label(holder, text=text, font=font, bg=bg, fg=fg,
                 padx=0, pady=0, anchor="w").pack()
        rule = tk.Frame(holder, bg=fg, height=1)
        rule.place(x=0, y=max(0, font.metrics("ascent") - 1),
                   width=font.measure(text), height=1)
        holder.pack(side="left")

    # ── Overlay: загрузка ────────────────────────────────────────────────────

    def _show_loading(self) -> None:
        """Показывает 'перевожу…' сразу после детекта горячей клавиши."""
        overlay = self._create_overlay_window()
        text = tk.Text(
            overlay, wrap="word", font=(OVERLAY_FONT, OVERLAY_SIZE),
            bg=BG_COLOR, fg=TEXT_COLOR,
            relief="flat", borderwidth=0,
            highlightthickness=0, padx=0, pady=0,
            width=20, height=1,
        )
        text.insert("1.0", "⏳ перевожу…")
        text.configure(state="disabled")
        text.pack()
        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._start_mouse_monitor()

    # ── Overlay: результат перевода ─────────────────────────────────────────

    def _show_overlay(self, translation: str) -> None:
        """
        Показывает перевод в оверлее с сохранённой структурой: строки, отступы,
        форматирование. Перевод автоматически копируется в буфер.
        """
        overlay = self._create_overlay_window()
        self._render(overlay, translation, HL_COLOR, TEXT_COLOR)

        # автокопирование — в том же виде, что и на экране
        self.root.clipboard_clear()
        self.root.clipboard_append(translation)

        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._start_mouse_monitor()

    # ── Overlay: ошибка ──────────────────────────────────────────────────────

    def _show_error(self, msg: str) -> None:
        """Показывает ошибку в оверлее."""
        overlay = self._create_overlay_window()
        self._render(overlay, f"⚠ {msg}", ERROR_BG, ERROR_FG)
        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._start_mouse_monitor()

    # ── Quit hotkey ──────────────────────────────────────────────────────────

    def _check_quit(self) -> None:
        """Выход по Ctrl+Shift+Q."""
        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & KEY_PRESSED)
        shift = bool(user32.GetAsyncKeyState(0x10) & KEY_PRESSED)
        q = bool(user32.GetAsyncKeyState(0x51) & KEY_PRESSED)
        if ctrl and shift and q:
            self.running = False
            self.root.quit()

    # ── Start ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Запуск основного цикла tkinter."""
        try:
            self.root.mainloop()
        finally:
            self.running = False


def ensure_single_instance() -> bool:
    """Проверка единственного экземпляра через мьютекс Windows."""
    kernel32.CreateMutexW(None, False, "Local\\InstantTranslator_Mutex")
    if ctypes.get_last_error() == 183:
        return False
    return True


if __name__ == "__main__":
    if not ensure_single_instance():
        print("⚠ Instant Translator уже запущен.")
        sys.exit(0)

    app = InstantTranslator()
    app.run()
