#!/usr/bin/env python3
"""
Instant Translator — system-wide translation utility.
Выдели текст → Ctrl+C (копирует) → Ctrl+C (переводит) → оверлей с переводом.

Чистый Python, zero external dependencies.
Работает в любой программе: браузер, IDE, терминал, игры, PDF-ридеры.
"""

import ctypes
import json
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
import urllib.parse
import urllib.request

# ─── Configuration ───────────────────────────────────────────────────────────
DOUBLE_PRESS_MS = 500           # Окно для двойного нажатия Ctrl+C (мс)
POLL_INTERVAL = 0.025           # 25ms — частота опроса клавиш
OVERLAY_AUTO_CLOSE_MS = 1000    # Авто-закрытие через N мс (если курсор не на оверлее)
OVERLAY_MAX_CHARS = 3000        # Макс. длина текста для перевода
OVERLAY_MAX_WIDTH_CHARS = 60   # Макс. ширина оверлея в символах (перенос строки)
OVERLAY_ALPHA = 0.94            # 6% прозрачности
BG_COLOR = "#FFFFF5"            # фон окна (максимально нейтральный, почти невидим при alpha)
TEXT_COLOR = "#333333"
HL_COLOR = "#FFFFE0"            # цвет «выделения» перевода (жёлтый маркер)


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


class InstantTranslator:
    """Основной класс — горячая клавиша + перевод + оверлей."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("InstantTranslator")

        self.last_press_time: float = 0.0
        self.prev_c_down: bool = False
        self.running = True
        self.overlay: tk.Toplevel | None = None
        self.overlay_active: bool = False
        self.close_timer: str | None = None

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
        # нормализация пробелов: \n, \r, \t, серии пробелов → один пробел
        text = re.sub(r'\s+', ' ', text).strip()[:OVERLAY_MAX_CHARS]
        if not text:
            return

        self._show_loading()

        thread = threading.Thread(
            target=self._do_translate,
            args=(text,),
            daemon=True,
        )
        thread.start()

    def _get_clipboard_text(self) -> str | None:
        """Безопасно читает текст из буфера обмена (3 попытки)."""
        for attempt in range(3):
            try:
                return self.root.clipboard_get()
            except tk.TclError:
                time.sleep(0.05)
        return None

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

    def _do_translate(self, text: str) -> None:
        """
        Переводит текст. Поддерживает только ru ↔ en.
        1) Определяет язык через авто-запрос
        2) Если ru → переводит на en, если en → переводит на ru
        3) Остальные языки → ошибка
        """
        SUPPORTED = {"ru", "en"}
        try:
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

            self.root.after(0, self._show_overlay, text, result)
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

        # отслеживание мыши для автозакрытия
        overlay.bind("<Enter>", self._on_mouse_enter)
        overlay.bind("<Leave>", self._on_mouse_leave)

        self.overlay = overlay
        self.overlay_active = True
        return overlay

    def _setup_close_timer(self, delay_ms: int = OVERLAY_AUTO_CLOSE_MS) -> None:
        """Запускает таймер закрытия оверлея."""
        self._cancel_close_timer()
        self.close_timer = self.overlay.after(delay_ms, self._close_overlay)

    def _cancel_close_timer(self) -> None:
        """Отменяет таймер закрытия."""
        if self.close_timer:
            try:
                self.overlay.after_cancel(self.close_timer)
            except tk.TclError:
                pass
            self.close_timer = None

    def _on_mouse_enter(self, _event=None) -> None:
        """Курсор зашёл на оверлей — отменяем таймер."""
        self._cancel_close_timer()

    def _on_mouse_leave(self, _event=None) -> None:
        """Курсор покинул оверлей — через 50ms проверяем, правда ли ушёл."""
        self.overlay.after(50, self._check_mouse_position)

    def _check_mouse_position(self) -> None:
        """Проверяет, действительно ли мышь за пределами оверлея (по bbox)."""
        if not self.overlay:
            return
        try:
            mx = self.overlay.winfo_pointerx()
            my = self.overlay.winfo_pointery()
            ox = self.overlay.winfo_rootx()
            oy = self.overlay.winfo_rooty()
            ow = self.overlay.winfo_width()
            oh = self.overlay.winfo_height()
            if ox <= mx <= ox + ow and oy <= my <= oy + oh:
                return
            self._setup_close_timer()
        except tk.TclError:
            pass

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

    def _close_overlay(self, _event=None) -> None:
        """Закрывает оверлей и сбрасывает флаги."""
        if self.overlay:
            try:
                self._cancel_close_timer()
                self.overlay.destroy()
            except tk.TclError:
                pass
            self.overlay = None
            self.overlay_active = False

    # ── Overlay: загрузка ────────────────────────────────────────────────────

    def _show_loading(self) -> None:
        """Показывает 'перевожу…' сразу после детекта горячей клавиши."""
        overlay = self._create_overlay_window()
        text = tk.Text(
            overlay, wrap="word", font=("Segoe UI", 11),
            bg=BG_COLOR, fg=TEXT_COLOR,
            relief="flat", borderwidth=0,
            highlightthickness=0, padx=0, pady=0,
            width=12, height=1,
        )
        text.insert("1.0", "⏳ перевожу…")
        text.configure(state="disabled")
        text.pack()
        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._setup_close_timer(OVERLAY_AUTO_CLOSE_MS)

    # ── Overlay: результат перевода ─────────────────────────────────────────

    def _show_overlay(self, _original: str, translation: str) -> None:
        """
        Показывает перевод в оверлее — Label подстраивается под пиксельную ширину текста.
        Перевод автоматически копируется в буфер.
        """
        overlay = self._create_overlay_window()

        # измеряем ширину для переноса
        font = tkfont.Font(family="Segoe UI", size=12)
        wraplength = font.measure("0" * OVERLAY_MAX_WIDTH_CHARS)

        label = tk.Label(
            overlay,
            text=translation,
            font=("Segoe UI", 12),
            bg=HL_COLOR,            # жёлтый фон впритык под буквами
            fg=TEXT_COLOR,
            padx=0, pady=0,
            wraplength=wraplength,
            justify="left",
            cursor="xterm",
        )
        label.pack()

        # автокопирование
        self.root.clipboard_clear()
        self.root.clipboard_append(translation)

        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._setup_close_timer(OVERLAY_AUTO_CLOSE_MS)

    # ── Overlay: ошибка ──────────────────────────────────────────────────────

    def _show_error(self, msg: str) -> None:
        """Показывает ошибку в оверлее."""
        overlay = self._create_overlay_window()
        text = tk.Text(
            overlay, wrap="word", font=("Segoe UI", 10),
            bg="#FFF0F0", fg="#CC3333",
            relief="flat", borderwidth=0,
            highlightthickness=0, padx=2, pady=2,
            width=30, height=1,
        )
        text.insert("1.0", f"⚠ {msg}")
        text.configure(state="disabled")
        text.pack()
        self._position_above_cursor()
        overlay.deiconify()
        overlay.lift()
        self._setup_close_timer(4000)

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
