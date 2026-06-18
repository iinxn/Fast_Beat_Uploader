import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

from utils.consts import (
    APP_TITLE,
    AUDIO_BITRATE_OPTIONS,
    AUDIO_SAMPLE_RATE_OPTIONS,
    AUDIO_EXTENSIONS,
    HORIZONTAL_PRESETS,
    IMAGE_EXTENSIONS,
    VERTICAL_PRESETS,
    VIDEO_PRESET_OPTIONS,
)
from utils.paths import USER_DATA_DIR, safe_filename
from services.ffmpeg import (
    build_ffmpeg_command,
    get_ffmpeg_path,
    get_ffprobe_path,
    parse_ffmpeg_duration,
    parse_ffmpeg_progress,
)
from services.presets import PresetStore
from services.settings import SettingsStore
from ui.dialogs import YouTubeUploadDialog

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self) -> None:
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1020, 720)

        self._auto_output_path: Optional[str] = ""
        self._suppress_output_trace = False
        self._render_proc: Optional[subprocess.Popen] = None
        self._render_cancelled = False
        self._render_total_duration: float = 0.0

        self.settings = SettingsStore()

        self.video_title = tk.StringVar()
        self.default_output_dir = tk.StringVar(value=self._initial_output_dir())
        self.image_path = tk.StringVar()
        self.audio_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.render_horizontal = tk.BooleanVar(value=True)
        self.render_vertical = tk.BooleanVar(value=False)
        self.preset = tk.StringVar(value="1080p")
        self.custom_width = tk.StringVar(value="1920")
        self.custom_height = tk.StringVar(value="1080")
        self.fps = tk.StringVar(value="30")
        self.video_crf = tk.StringVar(value="18")
        self.video_preset = tk.StringVar(value="ultrafast")
        self.audio_bitrate = tk.StringVar(value="320")
        self.audio_sample_rate = tk.StringVar(value="44100")
        self.loop_audio = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Готово")

        self.preset_store = PresetStore()

        self._build_ui()
        self._bind_traces()
        self._setup_drag_drop()
        self._refresh_resolution_fields()
        self._update_output_default(force=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if not os.path.exists(get_ffmpeg_path()) or not os.path.exists(get_ffprobe_path()):
            self.status.set("ffmpeg/ffprobe не найдены рядом с проектом")
            self._log("ffmpeg/ffprobe не найдены в папке проекта. Положи их в ./ffmpeg")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        main = ctk.CTkFrame(self, corner_radius=18)
        main.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(main, corner_radius=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(main, corner_radius=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        self._build_top_card(left)
        self._build_files_card(left)
        self._build_render_card(left)
        self._build_action_card(left)
        self._build_right_panel(right)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w", padx=20, pady=16)
        ctk.CTkLabel(title_block, text="Fast Beats Render", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(title_block, text="Видео из картинки и аудио + загрузка на YouTube", text_color=("#64748b", "#a3a3a3")).pack(anchor="w", pady=(4, 0))

        theme_block = ctk.CTkFrame(header, fg_color="transparent")
        theme_block.grid(row=0, column=1, sticky="e", padx=20, pady=16)
        ctk.CTkLabel(theme_block, text="Тема").pack(anchor="e")
        self.theme_switch = ctk.CTkSegmentedButton(theme_block, values=["System", "Light", "Dark"], command=ctk.set_appearance_mode, width=220)
        self.theme_switch.set("System")
        self.theme_switch.pack(anchor="e", pady=(4, 0))

    def _build_top_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(1, weight=1)

        self._label(card, "Название видео", 0, 0)
        ctk.CTkEntry(card, textvariable=self.video_title, placeholder_text="Например: My video").grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)

        self._label(card, "Папка по умолчанию", 1, 0)
        ctk.CTkEntry(card, textvariable=self.default_output_dir).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)
        ctk.CTkButton(card, text="Выбрать", width=110, command=self._pick_default_folder).grid(row=1, column=2, padx=(10, 0), pady=6)

    def _build_files_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(1, weight=1)

        self._label(card, "Картинка", 0, 0)
        ctk.CTkEntry(card, textvariable=self.image_path, placeholder_text="Выбери изображение...").grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)
        ctk.CTkButton(card, text="Открыть", width=110, command=self._pick_image).grid(row=0, column=2, padx=(10, 0), pady=6)

        self._label(card, "Аудио", 1, 0)
        ctk.CTkEntry(card, textvariable=self.audio_path, placeholder_text="Выбери аудио...").grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)
        ctk.CTkButton(card, text="Открыть", width=110, command=self._pick_audio).grid(row=1, column=2, padx=(10, 0), pady=6)

        self._label(card, "Файл результата", 2, 0)
        output_entry = ctk.CTkEntry(card, textvariable=self.output_path, placeholder_text="Путь сохранения MP4")
        output_entry.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=6)
        output_entry.bind("<Key>", lambda _e: self._mark_manual_output())
        ctk.CTkButton(card, text="Сохранить как", width=110, command=self._pick_output).grid(row=2, column=2, padx=(10, 0), pady=6)

        self.dual_output_hint = ctk.CTkLabel(
            card,
            text="",
            text_color=("#64748b", "#94a3b8"),
            justify="left",
        )
        self.dual_output_hint.grid(row=3, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=(0, 4))

    def _build_render_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(1, weight=1)

        self._label(card, "Ориентация", 0, 0)
        orient_frame = ctk.CTkFrame(card, fg_color="transparent")
        orient_frame.grid(row=0, column=1, columnspan=3, sticky="w", padx=(12, 0), pady=6)
        ctk.CTkCheckBox(orient_frame, text="Горизонтальное", variable=self.render_horizontal,
                        command=self._on_orientation_change).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(orient_frame, text="Вертикальное", variable=self.render_vertical,
                        command=self._on_orientation_change).pack(side="left")

        self._label(card, "Пресет", 1, 0)
        ctk.CTkOptionMenu(card, variable=self.preset, values=list(HORIZONTAL_PRESETS.keys()) + ["Свой размер"],
                          command=lambda _v: self._refresh_resolution_fields()).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=6)

        self._label(card, "Ширина", 1, 2)
        self.width_entry = ctk.CTkEntry(card, textvariable=self.custom_width, width=120)
        self.width_entry.grid(row=1, column=3, sticky="w", padx=(12, 0), pady=6)

        self._label(card, "Высота", 2, 0)
        self.height_entry = ctk.CTkEntry(card, textvariable=self.custom_height, width=120)
        self.height_entry.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=6)

        self._label(card, "FPS", 2, 2)
        ctk.CTkEntry(card, textvariable=self.fps, width=120).grid(row=2, column=3, sticky="w", padx=(12, 0), pady=6)

        self._label(card, "Качество (CRF)", 3, 0)
        crf_row = ctk.CTkFrame(card, fg_color="transparent")
        crf_row.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=6)
        crf_row.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(crf_row, textvariable=self.video_crf, width=30).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(crf_row, text="← лучше", text_color=("#64748b", "#94a3b8"), font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="w", padx=(6, 2))
        ctk.CTkSlider(crf_row, from_=0, to=51, number_of_steps=51, command=self._on_crf_change).grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkLabel(crf_row, text="хуже →", text_color=("#64748b", "#94a3b8"), font=ctk.CTkFont(size=11)).grid(row=0, column=3, sticky="e", padx=(2, 0))

        self._label(card, "Скорость сжатия", 4, 0)
        ctk.CTkOptionMenu(card, variable=self.video_preset, values=VIDEO_PRESET_OPTIONS).grid(row=4, column=1, sticky="w", padx=(12, 0), pady=6)
        ctk.CTkLabel(card, text="быстрее = меньше качество", text_color=("#64748b", "#94a3b8"), font=ctk.CTkFont(size=11)).grid(row=4, column=2, columnspan=2, sticky="w", padx=(8, 0))

        self._label(card, "Битрейт аудио", 5, 0)
        ctk.CTkOptionMenu(card, variable=self.audio_bitrate, values=AUDIO_BITRATE_OPTIONS).grid(row=5, column=1, sticky="w", padx=(12, 0), pady=6)

        self._label(card, "Частота аудио", 5, 2)
        ctk.CTkOptionMenu(card, variable=self.audio_sample_rate, values=AUDIO_SAMPLE_RATE_OPTIONS).grid(row=5, column=3, sticky="w", padx=(12, 0), pady=6)

        ctk.CTkSwitch(card, text="Обрезать по длине аудио", variable=self.loop_audio).grid(row=6, column=0, columnspan=4, sticky="w", padx=4, pady=(12, 2))

    def _build_action_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(0, weight=2)
        card.grid_columnconfigure(1, weight=2)
        card.grid_columnconfigure(2, weight=1)  # reset is narrower and separated

        # "Создать видео" and "Отменить рендер" share the same cell — only one visible at a time
        btn_cell = ctk.CTkFrame(card, fg_color="transparent")
        btn_cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        btn_cell.grid_columnconfigure(0, weight=1)

        self._render_btn = ctk.CTkButton(btn_cell, text="Создать видео", height=42, command=self._start_render)
        self._render_btn.grid(row=0, column=0, sticky="ew")

        self._stop_btn = ctk.CTkButton(btn_cell, text="Отменить рендер", height=42,
                                       fg_color="#dc2626", hover_color="#b91c1c",
                                       command=self._cancel_render)
        self._stop_btn.grid(row=0, column=0, sticky="ew")
        self._stop_btn.grid_remove()  # hidden until rendering starts

        ctk.CTkButton(card, text="Открыть папку", height=42, command=self._open_output_folder).grid(row=0, column=1, sticky="ew", padx=6)
        ctk.CTkButton(card, text="Сбросить", height=42, fg_color="#334155", hover_color="#1f2937", command=self._reset).grid(row=0, column=2, sticky="ew", padx=(24, 0))

    def _build_right_panel(self, parent) -> None:
        status_card = self._card(parent)
        status_card.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 12))
        status_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(status_card, text="Статус", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(status_card, textvariable=self.status, wraplength=360, justify="left").grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.progress_bar = ctk.CTkProgressBar(status_card, mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(10, 4))
        self.progress_bar.grid_remove()  # hidden until rendering starts

        info_card = self._card(parent)
        info_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        info_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(info_card, text="Подсказка", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            info_card,
            text=(
                "— Картинка масштабируется автоматически\n"
                "— Качество (CRF): 0 = максимум, 51 = минимум\n"
                "— Битрейт аудио: выше = лучше звук\n"
                "— Скорость сжатия: быстрее = больше файл\n"
                "— Частота аудио: обычно 44100 или 48000"
            ),
            justify="left", text_color=("#64748b", "#cbd5e1"),
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        log_card = self._card(parent)
        log_card.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_card, text="Лог рендера", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        self.log_box = ctk.CTkTextbox(log_card, wrap="word", corner_radius=12)
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.log_box.insert("end", "Здесь появится вывод ffmpeg...")
        self.log_box.configure(state="disabled")

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, corner_radius=18)

    def _label(self, parent, text: str, row: int, column: int):
        ctk.CTkLabel(parent, text=text, anchor="w").grid(row=row, column=column, sticky="w", padx=(12, 0), pady=6)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _bind_traces(self):
        for var in (self.video_title, self.default_output_dir, self.image_path, self.audio_path):
            var.trace_add("write", lambda *_: self._update_output_default())

    def _mark_manual_output(self):
        self._auto_output_path = None

    def _on_crf_change(self, value: float):
        self.video_crf.set(str(int(round(value))))

    def _on_orientation_change(self):
        """Called when either orientation checkbox changes."""
        # Ensure at least one orientation is always selected
        if not self.render_horizontal.get() and not self.render_vertical.get():
            self.render_horizontal.set(True)
        self._refresh_resolution_fields()
        self._update_dual_output_hint()

    @staticmethod
    def _default_videos_dir() -> str:
        return os.path.join(os.path.expanduser("~"), "Videos")

    def _initial_output_dir(self) -> str:
        """The folder to start with: the saved one (if it still exists), else ~/Videos."""
        saved = self.settings.get("default_output_dir", "")
        if saved and os.path.isdir(saved):
            return saved
        return self._default_videos_dir()

    def _save_default_folder(self):
        """Persist the current default output folder so it survives restarts."""
        folder = self.default_output_dir.get().strip()
        if folder:
            self.settings.set("default_output_dir", folder)
            self.settings.save()

    def _on_close(self):
        """Save preferences before exiting."""
        self._save_default_folder()
        self.destroy()

    def _pick_default_folder(self):
        path = filedialog.askdirectory(title="Выберите папку по умолчанию")
        if path:
            self.default_output_dir.set(path)
            self._save_default_folder()
            self._update_output_default(force=True)

    def _pick_image(self):
        path = filedialog.askopenfilename(
            title="Выберите картинку",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.avif"), ("All files", "*.*")],
        )
        if path:
            self.image_path.set(path)
            self._update_output_default(force=True)

    def _pick_audio(self):
        path = filedialog.askopenfilename(
            title="Выберите аудио",
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma"), ("All files", "*.*")],
        )
        if path:
            self.audio_path.set(path)
            self._update_output_default(force=True)

    def _pick_output(self):
        initial_dir = self.default_output_dir.get().strip()
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.getcwd()
        suggested_name = safe_filename(self.video_title.get()) if self.video_title.get().strip() else "video"
        path = filedialog.asksaveasfilename(
            title="Сохранить видео как",
            defaultextension=".mp4",
            initialdir=initial_dir,
            initialfile=f"{suggested_name}.mp4",
            filetypes=[("MP4 video", "*.mp4")],
        )
        if path:
            self._auto_output_path = None
            self.output_path.set(path)

    def _update_output_default(self, force: bool = False):
        if self._suppress_output_trace:
            return
        current = self.output_path.get().strip()
        if not force and self._auto_output_path is None and current:
            return

        folder = self.default_output_dir.get().strip()
        if not folder or not os.path.isdir(folder):
            folder = os.getcwd()

        title = safe_filename(self.video_title.get()) if self.video_title.get().strip() else None
        if title:
            filename = f"{title}.mp4"
        elif self.image_path.get().strip():
            filename = os.path.splitext(os.path.basename(self.image_path.get().strip()))[0] + "_video.mp4"
        else:
            filename = "video.mp4"

        new_path = os.path.join(folder, filename)
        if new_path != current:
            self._suppress_output_trace = True
            self.output_path.set(new_path)
            self._suppress_output_trace = False
        self._auto_output_path = new_path
        self._update_dual_output_hint()

    def _refresh_resolution_fields(self):
        is_custom = self.preset.get() == "Свой размер"
        do_h = self.render_horizontal.get()
        do_v = self.render_vertical.get()
        both = do_h and do_v

        # In dual mode, custom dimensions are disabled — each orientation
        # uses its own preset values. In single mode, Custom is editable.
        self.width_entry.configure(state="normal" if is_custom and not both else "disabled")
        self.height_entry.configure(state="normal" if is_custom and not both else "disabled")

        if not is_custom:
            preset_name = self.preset.get()
            # Show horizontal dims when horizontal is selected (or both);
            # show vertical dims only when vertical is the sole selection.
            if do_h or both:
                dims = HORIZONTAL_PRESETS.get(preset_name)
            else:
                dims = VERTICAL_PRESETS.get(preset_name)
            if dims:
                self.custom_width.set(str(dims[0]))
                self.custom_height.set(str(dims[1]))

    def _update_dual_output_hint(self):
        """Show a note under the output field when both orientations are selected."""
        if self.render_horizontal.get() and self.render_vertical.get():
            base = os.path.splitext(os.path.basename(self.output_path.get() or "video.mp4"))[0]
            self.dual_output_hint.configure(
                text=f"Создастся 2 файла: {base}_horizontal.mp4  и  {base}_vertical.mp4"
            )
        else:
            self.dual_output_hint.configure(text="")

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def _setup_drag_drop(self) -> None:
        """Register the whole window as a drag-and-drop target for files."""
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_file_drop)
        self.dnd_bind("<<DragEnter>>", self._on_drop_enter)
        self.dnd_bind("<<DragLeave>>", self._on_drop_leave)

    def _parse_drop_paths(self, data: str) -> list[str]:
        """Parse tkinterdnd2 drop data (Tcl list format) into individual file paths."""
        try:
            # self.tk.splitlist handles Tcl-list escaping correctly (braces, quotes, etc.)
            return list(self.tk.splitlist(data))
        except Exception:
            # Fallback brace parser for edge cases
            paths: list[str] = []
            data = data.strip()
            i = 0
            while i < len(data):
                if data[i] == "{":
                    j = data.index("}", i + 1)
                    paths.append(data[i + 1 : j])
                    i = j + 1
                elif data[i] == " ":
                    i += 1
                else:
                    j = data.find(" ", i)
                    if j == -1:
                        paths.append(data[i:])
                        break
                    paths.append(data[i:j])
                    i = j + 1
            return [p for p in paths if p]

    def _on_file_drop(self, event) -> None:
        """Handle a file drop — auto-detect image or audio by extension."""
        paths = self._parse_drop_paths(event.data)
        for path in paths:
            path = path.strip()
            ext = os.path.splitext(path)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                self.image_path.set(path)
            elif ext in AUDIO_EXTENSIONS:
                self.audio_path.set(path)
        self._update_output_default(force=True)
        self.status.set("Готово")

    def _on_drop_enter(self, event) -> None:
        self.status.set("Отпусти файл...")

    def _on_drop_leave(self, event) -> None:
        self.status.set("Готово")

    # ------------------------------------------------------------------
    # Render busy state
    # ------------------------------------------------------------------

    def _set_render_busy(self, busy: bool) -> None:
        """Swap render↔cancel buttons and show/hide the progress bar."""
        if busy:
            self._render_btn.grid_remove()
            self._stop_btn.grid()
            self.progress_bar.set(0)
            self.progress_bar.grid()
        else:
            self._stop_btn.grid_remove()
            self._render_btn.grid()
            self.progress_bar.grid_remove()
            self._render_cancelled = False
            self._render_proc = None

    def _cancel_render(self) -> None:
        """Signal the running ffmpeg process to terminate."""
        self._render_cancelled = True
        proc = self._render_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self.status.set("Отмена рендера...")

    def _process_ffmpeg_line(self, line: str) -> None:
        """Parse one ffmpeg output line; update progress bar; suppress noisy per-frame lines."""
        if not line:
            return
        # Extract total duration from the "Duration:" header (appears once at startup)
        if self._render_total_duration == 0.0:
            dur = parse_ffmpeg_duration(line)
            if dur is not None:
                self._render_total_duration = dur
        # Per-frame progress line: update bar and skip logging (too noisy)
        pos = parse_ffmpeg_progress(line)
        if pos is not None:
            if self._render_total_duration > 0:
                self.progress_bar.set(min(pos / self._render_total_duration, 1.0))
            return
        self._log(line)

    def _open_output_folder(self):
        path = self.output_path.get().strip()
        folder = os.path.dirname(path) if path else self.default_output_dir.get().strip() or os.getcwd()
        if not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Папка не найдена")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _reset(self):
        self._auto_output_path = ""
        self.video_title.set("")
        self.default_output_dir.set(self._initial_output_dir())
        self.image_path.set("")
        self.audio_path.set("")
        self.output_path.set("")
        self.render_horizontal.set(True)
        self.render_vertical.set(False)
        self.preset.set("1080p")
        self.custom_width.set("1920")
        self.custom_height.set("1080")
        self.fps.set("30")
        self.video_crf.set("18")
        self.video_preset.set("ultrafast")
        self.audio_bitrate.set("320")
        self.audio_sample_rate.set("44100")
        self.loop_audio.set(True)
        self.status.set("Готово")
        self._clear_log()
        self._refresh_resolution_fields()
        self._update_output_default(force=True)
        self._update_dual_output_hint()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _get_render_jobs(self, base_output: str, h_width: int, h_height: int) -> list[tuple[int, int, str]]:
        """Return a list of (width, height, output_path) for each selected orientation.

        When both orientations are chosen, two files are produced:
          <base>_horizontal.mp4  and  <base>_vertical.mp4
        When only one orientation is chosen, the output_path is used as-is.
        """
        do_h = self.render_horizontal.get()
        do_v = self.render_vertical.get()
        is_custom = self.preset.get() == "Свой размер"
        preset_name = self.preset.get()

        def h_dims() -> tuple[int, int]:
            if is_custom:
                return h_width, h_height
            return HORIZONTAL_PRESETS.get(preset_name, (h_width, h_height))

        def v_dims() -> tuple[int, int]:
            if is_custom:
                return h_height, h_width  # swap width↔height for vertical
            return VERTICAL_PRESETS.get(preset_name, (h_height, h_width))

        if do_h and do_v:
            stem, ext = os.path.splitext(base_output)
            w_h, h_h = h_dims()
            w_v, h_v = v_dims()
            return [
                (w_h, h_h, stem + "_horizontal" + ext),
                (w_v, h_v, stem + "_vertical" + ext),
            ]
        if do_h:
            w, h = h_dims()
            return [(w, h, base_output)]
        w, h = v_dims()
        return [(w, h, base_output)]

    def _start_render(self):
        if not os.path.exists(get_ffmpeg_path()) or not os.path.exists(get_ffprobe_path()):
            messagebox.showerror("Ошибка", "Нужно положить ffmpeg.exe и ffprobe.exe в папку ./ffmpeg")
            return
        if not self.render_horizontal.get() and not self.render_vertical.get():
            messagebox.showerror("Ошибка", "Выбери хотя бы одну ориентацию")
            return
        if not self.image_path.get().strip():
            messagebox.showerror("Ошибка", "Выбери картинку")
            return
        if not self.audio_path.get().strip():
            messagebox.showerror("Ошибка", "Выбери аудио")
            return

        try:
            h_width = int(self.custom_width.get())
            h_height = int(self.custom_height.get())
            fps = int(self.fps.get())
            video_crf = int(self.video_crf.get())
            audio_bitrate = int(self.audio_bitrate.get())
            audio_sample_rate = int(self.audio_sample_rate.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Параметры качества должны быть числами")
            return

        if h_width <= 0 or h_height <= 0 or fps <= 0:
            messagebox.showerror("Ошибка", "Разрешение и FPS должны быть больше нуля")
            return
        if not (0 <= video_crf <= 51):
            messagebox.showerror("Ошибка", "CRF должен быть в диапазоне 0..51")
            return

        if not self.output_path.get().strip():
            self._update_output_default(force=True)
        base_output = self.output_path.get().strip()
        if not base_output:
            messagebox.showerror("Ошибка", "Не удалось определить путь сохранения")
            return

        jobs = self._get_render_jobs(base_output, h_width, h_height)

        # Create output directories upfront
        for _, _, out_path in jobs:
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)

        image_path = self.image_path.get().strip()
        audio_path = self.audio_path.get().strip()
        video_preset = self.video_preset.get()
        loop_audio = self.loop_audio.get()

        self._render_cancelled = False
        self.status.set("Рендер начался...")
        self._clear_log()
        self._set_render_busy(True)

        def worker():
            completed: list[str] = []
            try:
                for job_idx, (w, h, out_path) in enumerate(jobs, start=1):
                    if self._render_cancelled:
                        break

                    label = "горизонтальное" if w >= h else "вертикальное"
                    if len(jobs) > 1:
                        self.after(0, lambda lbl=label, idx=job_idx: self.status.set(f"Рендер {idx}/{len(jobs)}: {lbl}"))
                        self.after(0, lambda lbl=label, jw=w, jh=h: self._log(f"\n── {lbl.capitalize()} ({jw}×{jh}) ──"))

                    # Reset per-job progress state
                    self._render_total_duration = 0.0
                    self.after(0, lambda: self.progress_bar.set(0))

                    cmd = build_ffmpeg_command(
                        image_path=image_path,
                        audio_path=audio_path,
                        output_path=out_path,
                        width=w, height=h, fps=fps,
                        video_crf=video_crf,
                        video_preset=video_preset,
                        audio_bitrate_kbps=audio_bitrate,
                        audio_sample_rate=audio_sample_rate,
                        loop_audio=loop_audio,
                        fill_frame=(h > w),  # vertical → crop to fill, horizontal → letterbox
                    )
                    self.after(0, lambda c=cmd: self._log("Команда: " + " ".join(f'"{x}"' if " " in x else x for x in c)))

                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                    )
                    self._render_proc = proc
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        if self._render_cancelled:
                            proc.terminate()
                            break
                        text = line.rstrip()
                        self.after(0, lambda s=text: self._process_ffmpeg_line(s))

                    proc.wait()

                    if self._render_cancelled:
                        # Remove the incomplete output file
                        if os.path.exists(out_path):
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                        break

                    if proc.returncode != 0:
                        raise RuntimeError(f"ffmpeg завершился с кодом {proc.returncode}")

                    completed.append(out_path)

                if self._render_cancelled:
                    self.after(0, lambda: self.status.set("Рендер отменён"))
                elif completed:
                    done_msg = "Видео успешно создано" if len(completed) == 1 else (
                        "Созданы оба варианта:\n" + "\n".join(os.path.basename(p) for p in completed)
                    )
                    self.after(0, lambda: self.status.set("Готово: видео создано"))
                    self.after(0, lambda m=done_msg: messagebox.showinfo("Готово", m))
                    self.after(0, lambda paths=completed: self._after_render_success(paths))

            except Exception as e:
                err = str(e)
                self.after(0, lambda: self.status.set("Ошибка рендера"))
                self.after(0, lambda msg=err: messagebox.showerror("Ошибка", msg))
                self.after(0, lambda msg=err: self._log(f"ERROR: {msg}"))

            finally:
                self.after(0, lambda: self._set_render_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _after_render_success(self, output_paths: list[str]):
        title = self.video_title.get().strip()
        for path in output_paths:
            label = os.path.basename(path)
            if messagebox.askyesno("Загрузка", f"Залить на YouTube?\n{label}"):
                dlg = YouTubeUploadDialog(self, video_path=path, suggested_title=title, preset_store=self.preset_store)
                self.wait_window(dlg)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main() -> None:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
