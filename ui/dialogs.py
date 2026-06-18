import calendar
import os
import threading
import traceback
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from utils.consts import (
    CATEGORY_OPTIONS,
    DEFAULT_CATEGORY,
    DEFAULT_LANGUAGE,
    LANGUAGE_OPTIONS,
)
from services.presets import PresetStore, UploadPreset
from services.youtube import YoutubeService


# ---------------------------------------------------------------------------
# DateTimePickerDialog
# ---------------------------------------------------------------------------

class DateTimePickerDialog(ctk.CTkToplevel):
    """A modal dialog for picking a future date and time."""

    def __init__(self, master, initial: Optional[datetime] = None):
        super().__init__(master)
        self.title("Выбор даты и времени")
        self.geometry("470x470")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.result: Optional[datetime] = None
        self.current = initial or (datetime.now() + timedelta(hours=1))
        self.selected_date = self.current.date()

        self.year_var = tk.IntVar(value=self.current.year)
        self.month_var = tk.IntVar(value=self.current.month)
        self.hour_var = tk.IntVar(value=self.current.hour)
        self.minute_var = tk.IntVar(value=(self.current.minute // 5) * 5)

        self._build_ui()
        self._render_calendar()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=16)
        top.pack(fill="x", padx=16, pady=16)

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.pack(fill="x", pady=(10, 4), padx=12)
        ctk.CTkButton(nav, text="◀", width=40, command=self._prev_month).pack(side="left")
        self.month_label = ctk.CTkLabel(nav, text="", font=ctk.CTkFont(size=18, weight="bold"))
        self.month_label.pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=40, command=self._next_month).pack(side="right")

        controls = ctk.CTkFrame(top, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(controls, text="Год").grid(row=0, column=0, sticky="w")
        tk.Spinbox(controls, from_=2000, to=2100, width=8, textvariable=self.year_var, command=self._render_calendar).grid(row=1, column=0, padx=(0, 12), sticky="w")

        ctk.CTkLabel(controls, text="Месяц").grid(row=0, column=1, sticky="w")
        self.month_box = ttk.Combobox(
            controls, width=12, state="readonly",
            values=[f"{i:02d} - {calendar.month_name[i]}" for i in range(1, 13)],
        )
        self.month_box.grid(row=1, column=1, padx=(0, 12), sticky="w")
        self.month_box.current(self.current.month - 1)
        self.month_box.bind("<<ComboboxSelected>>", self._on_month_select)

        ctk.CTkLabel(controls, text="Час").grid(row=0, column=2, sticky="w")
        tk.Spinbox(controls, from_=0, to=23, width=6, format="%02.0f", textvariable=self.hour_var).grid(row=1, column=2, padx=(0, 12), sticky="w")

        ctk.CTkLabel(controls, text="Мин").grid(row=0, column=3, sticky="w")
        tk.Spinbox(controls, values=[f"{i:02d}" for i in range(0, 60, 5)], width=6, textvariable=self.minute_var).grid(row=1, column=3, sticky="w")

        ctk.CTkLabel(top, text="Выбери день").pack(anchor="w", padx=12, pady=(6, 0))
        self.calendar_frame = ctk.CTkFrame(top, corner_radius=12)
        self.calendar_frame.pack(fill="both", expand=True, padx=12, pady=12)

        bottom = ctk.CTkFrame(self, corner_radius=16)
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        self.preview_label = ctk.CTkLabel(bottom, text="")
        self.preview_label.pack(anchor="w", padx=12, pady=(12, 4))

        btns = ctk.CTkFrame(bottom, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btns, text="Сегодня", command=self._set_today).pack(side="left")
        ctk.CTkButton(btns, text="Отмена", fg_color="#334155", hover_color="#1f2937", command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="Выбрать", command=self._confirm).pack(side="right")

    def _on_month_select(self, _event=None):
        self.month_var.set(self.month_box.current() + 1)
        self._render_calendar()

    def _prev_month(self):
        month = self.month_var.get() - 1
        year = self.year_var.get()
        if month < 1:
            month, year = 12, year - 1
        self.year_var.set(year)
        self.month_var.set(month)
        self.month_box.current(month - 1)
        self._render_calendar()

    def _next_month(self):
        month = self.month_var.get() + 1
        year = self.year_var.get()
        if month > 12:
            month, year = 1, year + 1
        self.year_var.set(year)
        self.month_var.set(month)
        self.month_box.current(month - 1)
        self._render_calendar()

    def _set_today(self):
        now = datetime.now()
        self.year_var.set(now.year)
        self.month_var.set(now.month)
        self.month_box.current(now.month - 1)
        self.hour_var.set(now.hour)
        self.minute_var.set((now.minute // 5) * 5)
        self.selected_date = now.date()
        self._render_calendar()

    def _render_calendar(self):
        for widget in self.calendar_frame.winfo_children():
            widget.destroy()

        year = self.year_var.get()
        month = self.month_var.get()
        self.month_label.configure(text=f"{calendar.month_name[month]} {year}")

        for i, day in enumerate(["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]):
            ctk.CTkLabel(self.calendar_frame, text=day).grid(row=0, column=i, padx=3, pady=(6, 2))

        for r, week in enumerate(calendar.monthcalendar(year, month), start=1):
            for c, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self.calendar_frame, text="").grid(row=r, column=c, padx=3, pady=3)
                    continue
                is_selected = (
                    self.selected_date.year == year
                    and self.selected_date.month == month
                    and self.selected_date.day == day
                )
                ctk.CTkButton(
                    self.calendar_frame,
                    text=str(day),
                    width=44, height=34,
                    fg_color="#1d4ed8" if is_selected else None,
                    command=lambda d=day: self._select_day(d),
                ).grid(row=r, column=c, padx=3, pady=3)

        self._update_preview()

    def _select_day(self, day: int):
        self.selected_date = datetime(self.year_var.get(), self.month_var.get(), day).date()
        self._render_calendar()

    def _update_preview(self):
        self.preview_label.configure(text=f"Запланировано: {self.get_value().strftime('%d.%m.%Y %H:%M')}")

    def get_value(self) -> datetime:
        return datetime(
            self.year_var.get(), self.month_var.get(), self.selected_date.day,
            int(self.hour_var.get()), int(self.minute_var.get()),
        )

    def _confirm(self):
        try:
            self.result = self.get_value()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)


# ---------------------------------------------------------------------------
# PresetManagerDialog
# ---------------------------------------------------------------------------

class PresetManagerDialog(ctk.CTkToplevel):
    """A modal dialog for creating, editing and deleting upload presets."""

    def __init__(self, master, store: PresetStore):
        super().__init__(master)
        self.title("Управление пресетами")
        self.geometry("920x560")
        self.minsize(880, 520)
        self.transient(master)
        self.grab_set()
        self.store = store

        self.name_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.language_var = tk.StringVar(value=DEFAULT_LANGUAGE)
        self.category_var = tk.StringVar(value=DEFAULT_CATEGORY)
        self.description_box: Optional[ctk.CTkTextbox] = None
        self.presets_list: Optional[tk.Listbox] = None

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        root = ctk.CTkFrame(self, corner_radius=18)
        root.pack(fill="both", expand=True, padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=2)
        root.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(root, text="Пресеты загрузки", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        left = ctk.CTkFrame(root, corner_radius=16)
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 16))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(root, corner_radius=16)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 16))
        right.grid_columnconfigure(1, weight=1)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        ctk.CTkButton(btn_row, text="Новый", width=90, command=self._new_preset).pack(side="left")
        ctk.CTkButton(btn_row, text="Сохранить", width=110, command=self._save_preset).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Удалить", width=90, fg_color="#7f1d1d", hover_color="#991b1b", command=self._delete_preset).pack(side="left")

        self.presets_list = tk.Listbox(left, activestyle="none")
        self.presets_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.presets_list.bind("<<ListboxSelect>>", self._on_select)

        fields = [
            ("Название пресета", self.name_var, 0),
            ("Название видео", self.title_var, 1),
        ]
        for label, var, row in fields:
            ctk.CTkLabel(right, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=(12 if row == 0 else 4, 4))
            ctk.CTkEntry(right, textvariable=var).grid(row=row, column=1, sticky="ew", padx=12, pady=(12 if row == 0 else 4, 4))

        ctk.CTkLabel(right, text="Описание").grid(row=2, column=0, sticky="nw", padx=12, pady=4)
        self.description_box = ctk.CTkTextbox(right, height=130, corner_radius=12)
        self.description_box.grid(row=2, column=1, sticky="nsew", padx=12, pady=4)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right, text="Теги").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        ctk.CTkEntry(right, textvariable=self.tags_var, placeholder_text="через запятую").grid(row=3, column=1, sticky="ew", padx=12, pady=4)

        ctk.CTkLabel(right, text="Язык").grid(row=4, column=0, sticky="w", padx=12, pady=4)
        ctk.CTkOptionMenu(right, variable=self.language_var, values=list(LANGUAGE_OPTIONS.keys())).grid(row=4, column=1, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(right, text="Категория").grid(row=5, column=0, sticky="w", padx=12, pady=4)
        ctk.CTkOptionMenu(right, variable=self.category_var, values=list(CATEGORY_OPTIONS.keys())).grid(row=5, column=1, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(
            right,
            text="Пресет можно использовать как шаблон для быстрого заполнения полей в окне загрузки.",
            wraplength=500, justify="left", text_color=("#64748b", "#94a3b8"),
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 12))

        ctk.CTkButton(right, text="Закрыть", fg_color="#334155", hover_color="#1f2937", command=self.destroy).grid(
            row=7, column=1, sticky="e", padx=12, pady=(8, 12)
        )

    def _refresh_list(self, select_name: Optional[str] = None):
        if self.presets_list is None:
            return
        self.presets_list.delete(0, "end")
        names = self.store.names()
        for name in names:
            self.presets_list.insert("end", name)

        target = select_name or self.store.data.get("last_selected") or (names[0] if names else None)
        if target and target in names:
            idx = names.index(target)
            self.presets_list.selection_set(idx)
            self.presets_list.see(idx)
            self._load_preset(names[idx])

    def _on_select(self, _event=None):
        if not self.presets_list:
            return
        selection = self.presets_list.curselection()
        if selection:
            self._load_preset(self.presets_list.get(selection[0]))

    def _load_preset(self, name: str):
        preset = self.store.get(name)
        if not preset:
            return
        self.name_var.set(preset.name)
        self.title_var.set(preset.title)
        self.tags_var.set(", ".join(preset.tags))
        self.language_var.set(preset.language if preset.language in LANGUAGE_OPTIONS else DEFAULT_LANGUAGE)
        self.category_var.set(preset.category if preset.category in CATEGORY_OPTIONS else DEFAULT_CATEGORY)
        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", "end")
        self.description_box.insert("1.0", preset.description)

    def _collect_preset(self) -> UploadPreset:
        description = self.description_box.get("1.0", "end").strip() if self.description_box else ""
        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        return UploadPreset(
            name=self.name_var.get().strip(),
            title=self.title_var.get().strip(),
            description=description,
            tags=tags,
            language=self.language_var.get() or DEFAULT_LANGUAGE,
            category=self.category_var.get() or DEFAULT_CATEGORY,
        )

    def _new_preset(self):
        self.name_var.set("")
        self.title_var.set("")
        self.tags_var.set("")
        self.language_var.set(DEFAULT_LANGUAGE)
        self.category_var.set(DEFAULT_CATEGORY)
        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", "end")

    def _save_preset(self):
        try:
            preset = self._collect_preset()
            if not preset.name:
                raise ValueError("Укажи название пресета")
            self.store.upsert(preset)
            self._refresh_list(select_name=preset.name)
            messagebox.showinfo("Готово", "Пресет сохранён", parent=self)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)

    def _delete_preset(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Сначала выбери пресет", parent=self)
            return
        if not messagebox.askyesno("Удаление", f"Удалить пресет '{name}'?", parent=self):
            return
        self.store.delete(name)
        self._new_preset()
        self._refresh_list()


# ---------------------------------------------------------------------------
# YouTubeUploadDialog
# ---------------------------------------------------------------------------

class YouTubeUploadDialog(ctk.CTkToplevel):
    """A modal dialog for uploading a rendered video to YouTube with scheduling."""

    def __init__(self, master, video_path: str, suggested_title: str = "", preset_store: Optional[PresetStore] = None):
        super().__init__(master)
        self.title("Загрузка на YouTube")
        self.geometry("800x670")
        self.minsize(760, 620)
        self.transient(master)
        self.grab_set()

        self.service = YoutubeService()
        self.preset_store = preset_store or PresetStore()

        self.video_path = tk.StringVar(value=video_path)
        self.preset_var = tk.StringVar()
        self.title_var = tk.StringVar(value=suggested_title)
        self.tags_var = tk.StringVar()
        self.publish_at_var = tk.StringVar()
        self.language_var = tk.StringVar(value=DEFAULT_LANGUAGE)
        self.category_var = tk.StringVar(value=DEFAULT_CATEGORY)
        self.status_var = tk.StringVar(value="Готово к загрузке")
        self.description_text: Optional[ctk.CTkTextbox] = None
        self.log_box: Optional[ctk.CTkTextbox] = None
        self.preset_menu: Optional[ctk.CTkOptionMenu] = None
        self._cancel_btn: Optional[ctk.CTkButton] = None
        self._suppress_preset_trace = False

        self._build_ui()
        self._set_default_publish_time()
        self._refresh_presets()
        self._log("Окно загрузки открыто")

    def _build_ui(self):
        frame = ctk.CTkScrollableFrame(self, corner_radius=16)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Публикация на YouTube", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(4, 2)
        )
        # Show which file is being uploaded
        filename = os.path.basename(self.video_path.get()) if self.video_path.get() else ""
        ctk.CTkLabel(
            frame, text=filename,
            text_color=("#64748b", "#94a3b8"), font=ctk.CTkFont(size=13),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # ── Preset ──────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Шаблон").grid(row=2, column=0, sticky="w", pady=6)
        preset_row = ctk.CTkFrame(frame, fg_color="transparent")
        preset_row.grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)
        preset_row.grid_columnconfigure(0, weight=1)
        self.preset_menu = ctk.CTkOptionMenu(preset_row, variable=self.preset_var, values=["—"])
        self.preset_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(preset_row, text="Управление", width=120, command=self._open_preset_manager).grid(row=0, column=1)
        self.preset_var.trace_add("write", lambda *_: self._apply_selected_preset())

        # ── File ────────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Файл видео").grid(row=3, column=0, sticky="w", pady=6)
        ctk.CTkEntry(frame, textvariable=self.video_path).grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=6)
        ctk.CTkButton(frame, text="Обзор...", width=110, command=self._pick_video).grid(row=3, column=2, pady=6)

        # ── Metadata ────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Название").grid(row=4, column=0, sticky="w", pady=6)
        ctk.CTkEntry(frame, textvariable=self.title_var, placeholder_text="Название видео на YouTube").grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=6
        )

        ctk.CTkLabel(frame, text="Описание").grid(row=5, column=0, sticky="nw", pady=6)
        self.description_text = ctk.CTkTextbox(frame, height=120, corner_radius=12)
        self.description_text.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=6)

        ctk.CTkLabel(frame, text="Теги").grid(row=6, column=0, sticky="w", pady=6)
        ctk.CTkEntry(frame, textvariable=self.tags_var, placeholder_text="тег1, тег2, тег3 — через запятую").grid(
            row=6, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=6
        )

        ctk.CTkLabel(frame, text="Язык").grid(row=7, column=0, sticky="w", pady=6)
        ctk.CTkOptionMenu(frame, variable=self.language_var, values=list(LANGUAGE_OPTIONS.keys())).grid(
            row=7, column=1, sticky="w", padx=(12, 0), pady=6
        )

        ctk.CTkLabel(frame, text="Категория").grid(row=8, column=0, sticky="w", pady=6)
        ctk.CTkOptionMenu(frame, variable=self.category_var, values=list(CATEGORY_OPTIONS.keys())).grid(
            row=8, column=1, sticky="w", padx=(12, 0), pady=6
        )

        # ── Publish date ────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Дата выхода").grid(row=9, column=0, sticky="w", pady=6)
        date_row = ctk.CTkFrame(frame, fg_color="transparent")
        date_row.grid(row=9, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=6)
        date_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(date_row, textvariable=self.publish_at_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(date_row, text="Выбрать дату", width=120, command=self._pick_datetime).grid(row=0, column=1)

        ctk.CTkLabel(
            frame,
            text="Видео загрузится как приватное и автоматически опубликуется в выбранное время.",
            text_color=("#64748b", "#94a3b8"), justify="left", wraplength=560,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(4, 8))

        # ── Status ──────────────────────────────────────────────────────
        self.status_label = ctk.CTkLabel(
            frame, textvariable=self.status_var,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.status_label.grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 4))

        # ── Log ─────────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Журнал загрузки").grid(row=12, column=0, sticky="nw", pady=(6, 0))
        self.log_box = ctk.CTkTextbox(frame, height=130, corner_radius=12)
        self.log_box.grid(row=12, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(6, 6))
        self.log_box.configure(state="disabled")

        # ── Buttons ─────────────────────────────────────────────────────
        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ctk.CTkButton(
            btns, text="Загрузить на YouTube", height=44,
            fg_color="#1d4ed8", hover_color="#1e40af",
            command=self._upload,
        ).pack(side="right")
        self._cancel_btn = ctk.CTkButton(
            btns, text="Отмена", height=44,
            fg_color="#334155", hover_color="#1f2937",
            command=self.destroy,
        )
        self._cancel_btn.pack(side="right", padx=(0, 10))
        # Reset Google login — handy when the token is revoked/expired.
        ctk.CTkButton(
            btns, text="Сбросить вход", height=44, width=130,
            fg_color="#7f1d1d", hover_color="#991b1b",
            command=self._reset_login,
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _reset_login(self):
        if not messagebox.askyesno(
            "Сброс входа",
            "Удалить сохранённый вход Google?\nПри следующей загрузке снова откроется окно авторизации.",
            parent=self,
        ):
            return
        removed = self.service.token_storage.clear()
        if removed:
            self._log("Сохранённый вход Google удалён")
            messagebox.showinfo("Готово", "Вход сброшен. При загрузке потребуется войти заново.", parent=self)
        else:
            messagebox.showinfo("Готово", "Сохранённого входа не найдено.", parent=self)

    def _set_default_publish_time(self):
        target = datetime.now() + timedelta(hours=1)
        self.publish_at_var.set(target.strftime("%d.%m.%Y %H:%M"))

    def _refresh_presets(self):
        names = self.preset_store.names() or ["—"]
        self.preset_menu.configure(values=names)
        last = self.preset_store.data.get("last_selected")
        # Suppress the trace so programmatic preset selection doesn't
        # overwrite fields the user may have already edited.
        self._suppress_preset_trace = True
        self.preset_var.set(last if last in names else names[0])
        self._suppress_preset_trace = False

    def _open_preset_manager(self):
        dlg = PresetManagerDialog(self, self.preset_store)
        self.wait_window(dlg)
        self._refresh_presets()
        self._apply_selected_preset()

    def _apply_selected_preset(self):
        if self._suppress_preset_trace:
            return
        name = self.preset_var.get().strip()
        if not name or name == "—":
            return
        preset = self.preset_store.get(name)
        if not preset:
            return
        if preset.title:
            self.title_var.set(preset.title)
        if preset.description:
            self.description_text.configure(state="normal")
            self.description_text.delete("1.0", "end")
            self.description_text.insert("1.0", preset.description)
        self.tags_var.set(", ".join(preset.tags))
        if preset.language in LANGUAGE_OPTIONS:
            self.language_var.set(preset.language)
        if preset.category in CATEGORY_OPTIONS:
            self.category_var.set(preset.category)
        self._log(f"Пресет применён: {preset.name}")

    def _log(self, text: str):
        if self.log_box is None:
            return
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            pass

    def _pick_video(self):
        path = filedialog.askopenfilename(
            parent=self, title="Выберите видео",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.video_path.set(path)

    def _pick_datetime(self):
        initial = self._parse_publish_at()
        picker = DateTimePickerDialog(self, initial=initial)
        self.wait_window(picker)
        if picker.result:
            value = picker.result.strftime("%d.%m.%Y %H:%M")
            self.publish_at_var.set(value)
            self._log(f"Дата выбрана: {value}")

    def _parse_publish_at(self) -> Optional[datetime]:
        try:
            return datetime.strptime(self.publish_at_var.get().strip(), "%d.%m.%Y %H:%M")
        except Exception:
            return None

    def _format_publish_at_rfc3339(self) -> str:
        dt = self._parse_publish_at()
        if dt is None:
            raise ValueError("Неверный формат даты публикации")
        if dt <= datetime.now() + timedelta(minutes=1):
            raise ValueError("Дата публикации должна быть в будущем")
        aware = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return aware.isoformat()

    def _upload(self):
        video_path = self.video_path.get().strip()
        if not os.path.exists(video_path):
            messagebox.showerror("Ошибка", "Видео файл не найден", parent=self)
            return

        title = self.title_var.get().strip()
        description = self.description_text.get("1.0", "end").strip() if self.description_text else ""
        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]

        try:
            publish_at = self._format_publish_at_rfc3339()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return

        category_id = CATEGORY_OPTIONS.get(self.category_var.get(), CATEGORY_OPTIONS[DEFAULT_CATEGORY])
        language_code = LANGUAGE_OPTIONS.get(self.language_var.get(), LANGUAGE_OPTIONS[DEFAULT_LANGUAGE])

        self.status_var.set("Подключение к YouTube...")
        self._log(f"Файл: {video_path}")
        self._log(f"Название: {title or 'Без названия'}")
        self._log(f"Дата публикации: {publish_at}")
        self._set_ui_busy(True)

        def worker():
            try:
                result = self.service.upload_video(
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    publish_at_rfc3339=publish_at,
                    category_id=category_id,
                    language_code=language_code,
                    log=lambda m: self.after(0, lambda msg=m: self._log(msg)),
                )
                video_id = result.get("id", "")
                self.after(0, lambda: self.status_var.set("Видео загружено"))
                self.after(0, lambda: self._log(f"Готово. Video ID: {video_id}"))
                self.after(0, lambda: messagebox.showinfo("Успех", f"Видео загружено: {video_id}", parent=self))
                self.after(0, self.destroy)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self.status_var.set("Ошибка загрузки"))
                self.after(0, lambda: self._log(f"ERROR: {err}"))
                self.after(0, lambda: self._log(traceback.format_exc()))
                self.after(0, lambda: messagebox.showerror("Ошибка", err, parent=self))
                self.after(0, lambda: self._set_ui_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _set_ui_busy(self, busy: bool):
        self._toggle_widgets(self, busy)

    def _toggle_widgets(self, widget, busy: bool):
        # Always keep the cancel button enabled so the user can close the window.
        if widget is self._cancel_btn:
            return
        try:
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkButton, ctk.CTkTextbox, ctk.CTkOptionMenu)):
                widget.configure(state="disabled" if busy else "normal")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._toggle_widgets(child, busy)
