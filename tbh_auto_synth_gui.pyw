from __future__ import annotations

import contextlib
import io
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import tbh_auto_synth as auto


LEVEL_LABEL_TO_KEY = {value["label"]: key for key, value in auto.LEVEL_RANGE_CHOICES.items()}
LEVEL_KEY_TO_LABEL = {key: value["label"] for key, value in auto.LEVEL_RANGE_CHOICES.items()}
CLICK_LABEL_TO_KEY = {
    "일반 클릭": "cursor",
}
CLICK_KEY_TO_LABEL = {value: key for key, value in CLICK_LABEL_TO_KEY.items()}

BG = "#f4f6f8"
PANEL_BG = "#ffffff"
HEADER_BG = "#22313f"
TEXT_DARK = "#1f2933"
TEXT_MUTED = "#5f6b7a"
ACCENT = "#34658a"
SUCCESS = "#1f8a5b"
WARNING = "#b7791f"
DANGER = "#b42318"
IDLE = "#607080"
BORDER = "#d9e2ec"


def pretty_log(message: str) -> str:
    replacements = (
        ("automation run started.", "자동 실행을 시작했습니다."),
        ("automation run finished. combines=", "자동 실행 완료. 합성 횟수="),
        ("GUI run started at", "GUI 실행 시작"),
        ("cube/combine UI already visible.", "큐브/합성 창이 이미 열려 있습니다."),
        ("open menu button was not found.", "메뉴 열기 버튼을 찾지 못했습니다."),
        ("cube button was not found.", "큐브 버튼을 찾지 못했습니다."),
        ("combine UI did not appear after opening cube.", "큐브를 열었지만 합성 창이 보이지 않습니다."),
        ("reward box opening is disabled.", "상자 열기가 꺼져 있습니다."),
        ("reward boxes opened:", "상자 열기 완료:"),
        ("close cube before reward boxes at", "상자 확인 전 큐브 창 닫기"),
        ("select auto-fill category:", "자동 채우기 분류 선택:"),
        ("select auto-fill category by dropdown offset:", "자동 채우기 분류 선택:"),
        ("select auto-fill category by open-menu offset:", "자동 채우기 분류 선택:"),
        ("auto-fill category dropdown was not found.", "자동 채우기 분류 버튼을 찾지 못했습니다."),
        ("auto-fill category option was not found:", "자동 채우기 분류 항목을 찾지 못했습니다:"),
        ("level range already", "합성 레벨 이미 선택됨"),
        ("select level range:", "합성 레벨 선택:"),
        ("fallback level range:", "잠금 감지, 하위 레벨로 변경:"),
        ("is locked on this screen.", "현재 화면에서 잠겨 있습니다."),
        ("auto-fill button is no longer visible.", "자동 채우기 버튼이 더 이상 보이지 않습니다."),
        ("nothing combinable after auto-fill.", "자동 채우기 후 합성할 아이템이 없습니다."),
        ("clear cube items:", "큐브 아이템 비우기:"),
        ("auto-fill did not produce a combinable set.", "자동 채우기 후 합성이 되지 않아 아이템을 뺍니다."),
        ("back button not found; click fallback clear position at", "돌아가기 버튼 인식 실패, 예비 위치 클릭"),
        ("back button was not found, and no fallback reference is available.", "돌아가기 버튼을 찾지 못했고 예비 위치도 계산할 수 없습니다."),
        ("combine started. category=", "합성 시작. 분류="),
        ("count=", "횟수="),
        ("max_combines_per_run reached; stopping this run to avoid an infinite loop.", "최대 합성 횟수에 도달해 이번 실행을 멈춥니다."),
        ("storage-to-bag button was not found.", "창고 < 가방 버튼을 찾지 못했습니다."),
        ("click inventory sort", "인벤토리 정렬 클릭"),
        ("bag first slot is empty after sorting; storage transfer is complete.", "정렬 후 첫 칸이 비어 있어 창고 이동이 완료된 것으로 판단했습니다."),
        ("bag still has items after transfer; trying another storage page.", "인벤토리에 아이템이 남아 있어 다음 창고 페이지를 시도합니다."),
        ("bag still has items after all configured storage pages were tried.", "설정된 창고 페이지를 모두 시도했지만 인벤토리에 아이템이 남아 있습니다."),
        ("screen area saved:", "화면 영역 저장:"),
        ("scan image saved:", "검사 이미지 저장:"),
        ("FOUND at", "인식됨"),
        ("missing", "인식 실패"),
        ("equipment", "장비"),
        ("material", "재료"),
    )
    for old, new in replacements:
        message = message.replace(old, new)
    return message


class TkQueueHandler(logging.Handler):
    def __init__(self, events: "queue.Queue[tuple]") -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.put(("log", pretty_log(self.format(record))))
        except Exception:
            pass


class ToggleButton(tk.Canvas):
    def __init__(self, parent: tk.Widget, text: str, variable: tk.BooleanVar, **kwargs) -> None:
        self.base_text = text
        self.variable = variable
        self.hovered = False
        self.text_font = tkfont.Font(family="Malgun Gothic", size=9)
        canvas_bg = kwargs.pop("bg", None)
        if canvas_bg is None:
            try:
                canvas_bg = parent.cget("bg")
            except tk.TclError:
                canvas_bg = PANEL_BG
        width = kwargs.pop("width", max(86, 54 + self.text_font.measure(text)))
        super().__init__(
            parent,
            width=width,
            height=28,
            bg=canvas_bg,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
            takefocus=1,
            **kwargs,
        )
        self.bind("<Button-1>", lambda _event: self.toggle())
        self.bind("<Return>", lambda _event: self.toggle())
        self.bind("<space>", lambda _event: self.toggle())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.variable.trace_add("write", lambda *_args: self.refresh())
        self.refresh()

    def toggle(self) -> None:
        self.variable.set(not self.variable.get())

    def _enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self.refresh()

    def _leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self.refresh()

    def _pill(self, x: int, y: int, width: int, height: int, fill: str, outline: str) -> None:
        radius = height // 2
        self.create_oval(x, y, x + height, y + height, fill=fill, outline=outline)
        self.create_oval(x + width - height, y, x + width, y + height, fill=fill, outline=outline)
        self.create_rectangle(x + radius, y, x + width - radius, y + height, fill=fill, outline=fill)
        self.create_line(x + radius, y, x + width - radius, y, fill=outline)
        self.create_line(x + radius, y + height, x + width - radius, y + height, fill=outline)

    def refresh(self) -> None:
        self.delete("all")
        enabled = self.variable.get()
        if enabled:
            track = "#dff3e9" if not self.hovered else "#d3ecdf"
            border = "#a8d8c0"
            knob = "#2d8a62"
            text = "#1f5f47"
        else:
            track = "#edf1f5" if not self.hovered else "#e4eaf0"
            border = "#cbd5df"
            knob = "#9aa6b2"
            text = "#52606d"

        self._pill(0, 3, 42, 22, track, border)
        knob_left = 22 if enabled else 3
        self.create_oval(knob_left, 6, knob_left + 16, 22, fill=knob, outline=knob)
        self.create_text(52, 14, anchor="w", text=self.base_text, fill=text, font=self.text_font)


class TaskBarHeroGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("태스크바 히어로 자동 합성")
        self.root.geometry("940x720")
        self.root.minsize(860, 640)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", ("Malgun Gothic", 10))

        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.running = False
        self.config = auto.load_config()

        target_key = str(self.config.get("target_level_range", "20_40"))
        self.status_var = tk.StringVar(value="대기 중")
        self.next_run_var = tk.StringVar(value="-")
        self.last_run_var = tk.StringVar(value="-")
        self.region_var = tk.StringVar(value=self._region_text(self.config))
        self.interval_minutes_var = tk.StringVar(value=str(int(self.config.get("interval_seconds", 1800)) // 60))
        self.equipment_var = tk.BooleanVar(value="equipment" in self.config.get("auto_fill_categories", []))
        self.material_var = tk.BooleanVar(value="material" in self.config.get("auto_fill_categories", []))
        self.force_level_var = tk.BooleanVar(value=bool(self.config.get("force_level_range_20_40", False)))
        self.open_boxes_var = tk.BooleanVar(value=bool(self.config.get("open_reward_boxes_before_combine", True)))
        self.close_cube_before_boxes_var = tk.BooleanVar(value=bool(self.config.get("close_cube_before_reward_boxes", True)))
        self.layout_search_var = tk.BooleanVar(value=bool(self.config.get("layout_independent_search", True)))
        self.level_range_var = tk.StringVar(value=LEVEL_KEY_TO_LABEL.get(target_key, "Lv.20~40"))
        self.screen_scale_var = tk.StringVar(value=str(self.config.get("game_screen_scale", "1x")))
        self.auto_follow_window_var = tk.BooleanVar(value=bool(self.config.get("auto_follow_window", True)))
        self.bring_window_to_front_var = tk.BooleanVar(value=bool(self.config.get("bring_window_to_front", True)))
        self.window_title_var = tk.StringVar(value=str(self.config.get("window_title_keyword", "TaskBarHero")))
        click_key = str(self.config.get("click_mode", "cursor"))
        self.click_mode_var = tk.StringVar(value=CLICK_KEY_TO_LABEL.get(click_key, "일반 클릭"))

        self.status_badge: tk.Label | None = None
        self.advanced_frame: tk.Frame | None = None
        self.advanced_toggle_button: ttk.Button | None = None
        self.log_panel: tk.Frame | None = None
        self.advanced_visible = False
        self.log_text: tk.Text
        self.start_button: ttk.Button
        self.once_button: ttk.Button
        self.stop_button: ttk.Button

        self._configure_logging()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)

    def _configure_logging(self) -> None:
        auto.LOG_DIR.mkdir(exist_ok=True)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not any(getattr(handler, "_tbh_gui_handler", False) for handler in root_logger.handlers):
            gui_handler = TkQueueHandler(self.events)
            gui_handler.setFormatter(logging.Formatter("%H:%M:%S  %(message)s"))
            gui_handler._tbh_gui_handler = True  # type: ignore[attr-defined]
            root_logger.addHandler(gui_handler)

        if not any(getattr(handler, "_tbh_file_handler", False) for handler in root_logger.handlers):
            file_handler = logging.FileHandler(auto.LOG_DIR / "task_bar_hero_auto.log", encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            file_handler._tbh_file_handler = True  # type: ignore[attr-defined]
            root_logger.addHandler(file_handler)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=BG)
        style.configure("TLabel", background=PANEL_BG, foreground=TEXT_DARK)
        style.configure("Muted.TLabel", background=PANEL_BG, foreground=TEXT_MUTED)
        style.configure("Value.TLabel", background=PANEL_BG, foreground=TEXT_DARK, font=("Malgun Gothic", 11, "bold"))
        style.configure("PageMuted.TLabel", background=BG, foreground=TEXT_MUTED)
        style.configure("Primary.TButton", font=("Malgun Gothic", 11, "bold"), padding=(14, 10))
        style.configure("Danger.TButton", font=("Malgun Gothic", 11, "bold"), padding=(14, 10))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Malgun Gothic", 11, "bold"), padding=(14, 10))
        style.map(
            "Accent.TButton",
            background=[("active", "#2a526f"), ("disabled", "#a6b7d0")],
            foreground=[("disabled", "#eef2f7")],
        )
        style.configure("TButton", padding=(10, 7))
        style.configure("TCheckbutton", background=PANEL_BG, foreground=TEXT_DARK)
        style.configure("TCombobox", padding=(4, 4))

        main = ttk.Frame(self.root, style="App.TFrame", padding=18)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=4, minsize=500)
        main.columnconfigure(1, weight=3, minsize=360)
        main.rowconfigure(2, weight=1)

        self._build_header(main)
        self._build_status_panel(main)
        left = tk.Frame(main, bg=BG)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
        left.columnconfigure(0, weight=1)
        right = tk.Frame(main, bg=BG)
        right.grid(row=2, column=1, sticky="nsew", pady=(0, 14))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        self._build_action_panel(left)
        self._build_settings_panel(left)
        self._build_region_panel(right)
        self._build_advanced_panel(right)
        self._build_log_panel(right)

        self._append_log("준비 완료. 게임 창을 켜고 인식 검사 또는 실행을 누르세요.")
        self._append_log("영역을 다시 잡아도 창 위치 추적은 계속 켜져 있고, 선택한 영역이 창 이동을 따라갑니다.")

    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Frame(parent, bg=BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text="태스크바 히어로 자동 합성",
            bg=BG,
            fg=TEXT_DARK,
            font=("Malgun Gothic", 18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")
        subtitle = tk.Label(
            header,
            text="상자 열기, 장비/재료 합성, 창고 이동을 화면 인식으로 실행합니다.",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 9),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.status_badge = tk.Label(
            header,
            textvariable=self.status_var,
            bg=IDLE,
            fg="white",
            padx=16,
            pady=8,
            font=("Malgun Gothic", 10, "bold"),
        )
        self.status_badge.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_status_panel(self, parent: ttk.Frame) -> None:
        panel = tk.Frame(parent, bg=BG)
        panel.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        panel.columnconfigure((0, 1, 2), weight=1)

        self._summary_item(panel, "현재 상태", self.status_var, 0)
        self._summary_item(panel, "다음 실행까지", self.next_run_var, 1)
        self._summary_item(panel, "마지막 실행", self.last_run_var, 2)

    def _build_action_panel(self, parent: tk.Frame) -> None:
        panel = self._section(parent, "실행")
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        panel.columnconfigure((0, 1), weight=1)

        self.start_button = ttk.Button(panel, text="자동 반복 시작", style="Accent.TButton", command=self.start_loop)
        self.start_button.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        self.once_button = ttk.Button(panel, text="한 번 실행", style="Primary.TButton", command=self.run_once)
        self.once_button.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 0))
        self.stop_button = ttk.Button(panel, text="중지", style="Danger.TButton", command=self.stop, state="disabled")
        self.stop_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        note = tk.Label(
            panel,
            text="실행 중에는 마우스 포인터가 클릭 위치로 이동합니다.",
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 9),
            justify="left",
            wraplength=280,
        )
        note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _build_settings_panel(self, parent: tk.Frame) -> None:
        panel = self._section(parent, "기본 설정")
        panel.grid(row=1, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1, uniform="settings")
        panel.columnconfigure(1, weight=1, uniform="settings")

        ttk.Label(panel, text="반복 간격", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        interval_field = tk.Frame(panel, bg=PANEL_BG)
        interval_field.grid(row=2, column=0, sticky="w")
        ttk.Spinbox(interval_field, from_=1, to=1440, textvariable=self.interval_minutes_var, width=8).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(interval_field, text="분", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(panel, text="합성 레벨", style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=(18, 0), pady=(0, 4))
        self.level_combo = ttk.Combobox(
            panel,
            textvariable=self.level_range_var,
            values=list(LEVEL_LABEL_TO_KEY.keys()),
            width=12,
            state="readonly",
        )
        self.level_combo.grid(row=2, column=1, sticky="w", padx=(18, 0))

        ttk.Label(panel, text="게임 창 크기", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(16, 4))
        ttk.Combobox(
            panel,
            textvariable=self.screen_scale_var,
            values=list(auto.SCREEN_SCALE_CHOICES.keys()),
            width=8,
            state="readonly",
        ).grid(row=4, column=0, sticky="w")

        ttk.Label(panel, text="자동화 옵션", style="Muted.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 4))
        option_row = tk.Frame(panel, bg=PANEL_BG)
        option_row.grid(row=6, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            option_row.columnconfigure(column, weight=1, uniform="basic_toggle")
        ToggleButton(option_row, "장비", self.equipment_var, width=88).grid(row=0, column=0, sticky="w")
        ToggleButton(option_row, "재료", self.material_var, width=88).grid(row=0, column=1, sticky="w")
        ToggleButton(option_row, "상자 먼저", self.open_boxes_var, width=108).grid(row=0, column=2, sticky="w")
        ToggleButton(option_row, "레벨 고정", self.force_level_var, width=108).grid(row=0, column=3, sticky="w")

        hint = tk.Label(
            panel,
            text="보통은 OFF 권장입니다. 자동 채우기가 아이템 레벨에 맞춰 합성 레벨을 조정합니다.",
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 9),
            justify="left",
            wraplength=280,
        )
        hint.grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_region_panel(self, parent: tk.Frame) -> None:
        panel = self._section(parent, "화면 영역")
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        panel.columnconfigure(0, weight=1)

        region_label = tk.Label(
            panel,
            textvariable=self.region_var,
            bg=PANEL_BG,
            fg=TEXT_DARK,
            font=("Malgun Gothic", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=330,
        )
        region_label.grid(row=1, column=0, sticky="ew")

        buttons = tk.Frame(panel, bg=PANEL_BG)
        buttons.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(buttons, text="영역 다시 잡기", command=self.set_screen_area).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="인식 검사", command=self.scan).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        tip = tk.Label(
            panel,
            text="큐브/합성창, 창고/가방, 전투 목록/보상 상자를 모두 포함하세요.",
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 9),
            justify="left",
            wraplength=330,
        )
        tip.grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _build_advanced_panel(self, parent: tk.Frame) -> None:
        panel = self._section(parent, "고급 설정")
        panel.grid(row=1, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)

        self.advanced_toggle_button = ttk.Button(panel, text="고급 설정 열기", command=self._toggle_advanced)
        self.advanced_toggle_button.grid(row=1, column=0, sticky="ew")

        body = tk.Frame(panel, bg=PANEL_BG)
        body.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self.advanced_frame = body

        ToggleButton(body, "창 위치 추적", self.auto_follow_window_var).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ToggleButton(body, "창 앞으로", self.bring_window_to_front_var).grid(row=0, column=1, sticky="w", pady=(0, 8), padx=(8, 0))

        ttk.Label(body, text="창 제목", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(body, textvariable=self.window_title_var, width=16).grid(row=2, column=0, sticky="ew", pady=(4, 10), padx=(0, 8))
        ttk.Label(body, text="클릭 방식", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=(4, 0), padx=(8, 0))
        ttk.Combobox(
            body,
            textvariable=self.click_mode_var,
            values=list(CLICK_LABEL_TO_KEY.keys()),
            width=22,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=(4, 10), padx=(8, 0))

        ToggleButton(body, "UI 자동 탐색", self.layout_search_var).grid(row=3, column=0, sticky="w", pady=(2, 8))
        ToggleButton(body, "상자 전 큐브 닫기", self.close_cube_before_boxes_var).grid(row=3, column=1, sticky="w", pady=(2, 8), padx=(8, 0))

        tools = tk.Frame(body, bg=PANEL_BG)
        tools.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        tools.columnconfigure((0, 1), weight=1)
        ttk.Button(tools, text="로그 폴더", command=self.open_logs).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(tools, text="설정 파일", command=self.open_config).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._set_advanced_visible(False)

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        panel = self._section(parent, "실행 기록")
        self.log_panel = panel
        panel.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        self.log_text = tk.Text(
            panel,
            height=10,
            wrap="word",
            state="disabled",
            font=("Malgun Gothic", 9),
            bg=PANEL_BG,
            fg=TEXT_DARK,
            relief="flat",
            padx=10,
            pady=8,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _summary_item(self, parent: tk.Frame, title: str, value: tk.StringVar, column: int) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 14, 0))
        tk.Label(frame, text=title, bg=BG, fg=TEXT_MUTED, font=("Malgun Gothic", 9)).pack(anchor="w")
        tk.Label(frame, textvariable=value, bg=BG, fg=TEXT_DARK, font=("Malgun Gothic", 11, "bold")).pack(anchor="w", pady=(2, 0))

    def _section(self, parent: tk.Widget, title: str | None) -> tk.Frame:
        frame = tk.Frame(parent, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER, padx=14, pady=12)
        frame.columnconfigure(0, weight=1)
        if title:
            label = tk.Label(frame, text=title, bg=PANEL_BG, fg=TEXT_DARK, font=("Malgun Gothic", 11, "bold"))
            label.grid(row=0, column=0, sticky="w", pady=(0, 10))
        return frame

    def _toggle_advanced(self) -> None:
        self._set_advanced_visible(not self.advanced_visible)

    def _set_advanced_visible(self, visible: bool) -> None:
        self.advanced_visible = visible
        if self.advanced_frame is not None:
            if visible:
                self.advanced_frame.grid()
            else:
                self.advanced_frame.grid_remove()
        if self.advanced_toggle_button is not None:
            self.advanced_toggle_button.configure(text="고급 설정 닫기" if visible else "고급 설정 열기")
        if self.log_panel is not None:
            if visible:
                self.log_panel.grid_remove()
            else:
                self.log_panel.grid()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "status":
                    self._set_status(event[1])
                elif kind == "next":
                    self.next_run_var.set(event[1])
                elif kind == "last":
                    self.last_run_var.set(event[1])
                elif kind == "running":
                    self._set_running(bool(event[1]))
                elif kind == "region":
                    self.region_var.set(event[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        if not self.status_badge:
            return
        color = IDLE
        if "실행" in text or "검사" in text:
            color = SUCCESS
        elif "중지" in text:
            color = WARNING
        elif "오류" in text:
            color = DANGER
        self.status_badge.configure(bg=color)

    def _set_running(self, value: bool) -> None:
        self.running = value
        running_state = "disabled" if value else "normal"
        stop_state = "normal" if value else "disabled"
        self.start_button.configure(state=running_state)
        self.once_button.configure(state=running_state)
        self.stop_button.configure(state=stop_state)

    def _region_text(self, config: dict) -> str:
        relative = config.get("search_region_from_window")
        if bool(config.get("auto_follow_window", True)) and isinstance(relative, dict):
            keyword = str(config.get("window_title_keyword", "TaskBarHero")).strip() or "TaskBarHero"
            left = int(relative.get("left", 0))
            top = int(relative.get("top", 0))
            width = int(relative.get("width", 0))
            height = int(relative.get("height", 0))
            return (
                f"창 추적 영역: {keyword} + "
                f"{left}, {top} / 크기 {width} x {height}"
            )
        region = config.get("search_region")
        if not region:
            if bool(config.get("auto_follow_window", True)):
                keyword = str(config.get("window_title_keyword", "TaskBarHero")).strip() or "TaskBarHero"
                return f"자동 창 추적: {keyword}"
            return "미설정"
        return f"좌표 {region['left']}, {region['top']} / 크기 {region['width']} x {region['height']}"

    def _has_runnable_region(self, config: dict) -> bool:
        return bool(config.get("search_region")) or bool(config.get("auto_follow_window", True))

    def _save_config_from_ui(self) -> dict | None:
        try:
            minutes = int(self.interval_minutes_var.get().strip())
            if minutes <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("설정 오류", "반복 간격은 1분 이상의 숫자로 입력하세요.")
            return None

        categories: list[str] = []
        if self.equipment_var.get():
            categories.append("equipment")
        if self.material_var.get():
            categories.append("material")
        if not categories:
            messagebox.showerror("설정 오류", "장비 합성 또는 재료 합성 중 하나 이상을 선택하세요.")
            return None

        label = self.level_range_var.get()
        target_level = LEVEL_LABEL_TO_KEY.get(label, "20_40")

        config = auto.load_config()
        config["interval_seconds"] = minutes * 60
        config["auto_fill_categories"] = categories
        config["force_level_range_20_40"] = bool(self.force_level_var.get())
        config["target_level_range"] = target_level
        config["locked_level_fallback"] = "lower"
        config["open_reward_boxes_before_combine"] = bool(self.open_boxes_var.get())
        config["close_cube_before_reward_boxes"] = bool(self.close_cube_before_boxes_var.get())
        config["game_screen_scale"] = self.screen_scale_var.get()
        config["layout_independent_search"] = bool(self.layout_search_var.get())
        config["reward_box_search_whole_region"] = bool(self.layout_search_var.get())
        config["auto_follow_window"] = bool(self.auto_follow_window_var.get())
        config["bring_window_to_front"] = bool(self.bring_window_to_front_var.get())
        config["window_title_keyword"] = self.window_title_var.get().strip() or "TaskBarHero"
        config["click_mode"] = CLICK_LABEL_TO_KEY.get(self.click_mode_var.get(), "cursor")
        auto.save_config(config)
        self.config = config
        self.region_var.set(self._region_text(config))
        return config

    def set_screen_area(self) -> None:
        if self.running:
            messagebox.showinfo("화면 영역", "자동 실행을 중지한 뒤 화면 영역을 변경하세요.")
            return
        dialog = RegionCaptureDialog(self.root)
        self.root.wait_window(dialog.window)
        if not dialog.region:
            return

        config = auto.load_config()
        config["search_region"] = dialog.region.to_config()
        config["reward_box_search_area_from_region"] = {
            "left": 0,
            "top": int(dialog.region.height * 0.52),
            "width": dialog.region.width,
            "height": int(dialog.region.height * 0.45),
        }
        config["auto_follow_window"] = True
        config["search_region_follow_window"] = True
        keyword = str(config.get("window_title_keyword", "TaskBarHero"))
        window_region = auto.find_window_region_by_title(keyword, config)
        if window_region:
            config["search_region_from_window"] = auto.relative_region_to_window(dialog.region, window_region)
            config["search_region_window_size"] = {
                "width": window_region.width,
                "height": window_region.height,
            }
        else:
            config["search_region_from_window"] = None
            config["search_region_window_size"] = None
        auto.save_config(config)
        self.config = config
        self.auto_follow_window_var.set(True)
        self.region_var.set(self._region_text(config))
        logging.info("screen area saved: %s", self.region_var.get())

    def _start_worker(self, mode: str) -> None:
        if self.running:
            return
        config = self._save_config_from_ui()
        if not config:
            return
        if not self._has_runnable_region(config):
            messagebox.showwarning("화면 영역", "창 위치 추적을 켜거나 실행 전에 화면 영역을 먼저 설정하세요.")
            return

        self.stop_event.clear()
        self.worker = threading.Thread(target=self._worker_main, args=(mode, config), daemon=True)
        self.worker.start()

    def start_loop(self) -> None:
        self._start_worker("loop")

    def run_once(self) -> None:
        self._start_worker("once")

    def scan(self) -> None:
        self._start_worker("scan")

    def stop(self) -> None:
        self.stop_event.set()
        self._set_status("중지 중")
        self.next_run_var.set("-")
        logging.info("중지 요청을 받았습니다. 현재 클릭 동작이 끝나면 멈춥니다.")

    def _worker_main(self, mode: str, config: dict) -> None:
        self.events.put(("running", True))
        self.events.put(("status", "버튼 검사 중" if mode == "scan" else "실행 중"))
        self.events.put(("next", "-"))
        try:
            auto.enable_dpi_awareness()
            auto.set_active_config(config)
            templates = auto.load_templates(config)
            if mode == "scan":
                region = auto.parse_region(None, config)
                if region is None and not config.get("search_region"):
                    raise RuntimeError("TaskBarHero 창을 찾지 못했습니다. 게임 창을 켜거나 영역 다시 잡기를 사용하세요.")
                self._run_scan(templates, region, config)
                return

            while not self.stop_event.is_set():
                region = auto.parse_region(None, config)
                if region is None and not config.get("search_region"):
                    raise RuntimeError("TaskBarHero 창을 찾지 못했습니다. 게임 창을 켜거나 영역 다시 잡기를 사용하세요.")
                started = time.strftime("%H:%M:%S")
                logging.info("GUI 실행 시작: %s", started)
                combines = auto.run_once(templates, region, config)
                self.events.put(("last", f"{time.strftime('%H:%M:%S')} / 합성 {combines}회"))
                if mode == "once":
                    break
                if self._wait_for_next_run(int(config.get("interval_seconds", 1800))):
                    break
        except Exception:
            logging.exception("자동 실행 중 오류가 발생했습니다.")
            self.events.put(("status", "오류 발생"))
        finally:
            if self.stop_event.is_set():
                self.events.put(("status", "중지됨"))
            elif mode == "scan":
                self.events.put(("status", "검사 완료"))
            else:
                self.events.put(("status", "대기 중"))
            self.events.put(("next", "-"))
            self.events.put(("running", False))

    def _run_scan(self, templates: dict, region: auto.Region | None, config: dict) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            auto.scan_templates(templates, region, config)
        for line in output.getvalue().splitlines():
            logging.info(line)

    def _wait_for_next_run(self, interval: int) -> bool:
        deadline = time.monotonic() + interval
        while not self.stop_event.is_set():
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                self.events.put(("next", "곧 실행"))
                return False
            minutes, seconds = divmod(remaining, 60)
            self.events.put(("next", f"{minutes:02d}분 {seconds:02d}초"))
            if self.stop_event.wait(1):
                return True
        return True

    def open_logs(self) -> None:
        auto.LOG_DIR.mkdir(exist_ok=True)
        os.startfile(auto.LOG_DIR)

    def open_config(self) -> None:
        if not auto.CONFIG_PATH.exists():
            auto.save_config(auto.DEFAULT_CONFIG.copy())
        os.startfile(auto.CONFIG_PATH)

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("종료", "자동 실행 중입니다. 중지하고 종료할까요?"):
                return
            self.stop_event.set()
        self.root.destroy()


class RegionCaptureDialog:
    def __init__(self, parent: tk.Tk) -> None:
        self.parent = parent
        self.region: auto.Region | None = None
        self.screen_region = auto.virtual_screen_region()
        self.start_point: tuple[int, int] | None = None
        self.rect_id: int | None = None
        self.size_id: int | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("화면 영역 설정")
        self.window.overrideredirect(True)
        self.window.geometry(
            f"{self.screen_region.width}x{self.screen_region.height}+{self.screen_region.left}+{self.screen_region.top}"
        )
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.34)
        self.window.grab_set()
        self.window.configure(bg="#101820")

        self.canvas = tk.Canvas(
            self.window,
            bg="#101820",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            24,
            24,
            anchor="nw",
            fill="#ffffff",
            font=("Malgun Gothic", 15, "bold"),
            text="화면 영역 설정: 드래그해서 전체 영역을 선택하세요",
        )
        self.canvas.create_text(
            24,
            58,
            anchor="nw",
            fill="#ffe08a",
            font=("Malgun Gothic", 11),
            text="큐브/합성창, 창고/가방, 전투 목록/보상 상자가 모두 포함되어야 합니다. 전투 목록만 잡으면 안 됩니다. 취소: Esc",
        )

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.focus_force()

    def _start_drag(self, event: tk.Event) -> None:
        self.start_point = (int(event.x), int(event.y))
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        if self.size_id is not None:
            self.canvas.delete(self.size_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#ff4d4f",
            width=4,
        )
        self.size_id = self.canvas.create_text(
            event.x + 10,
            event.y + 10,
            anchor="nw",
            fill="#ffffff",
            font=("Malgun Gothic", 11, "bold"),
            text="0 x 0",
        )

    def _drag(self, event: tk.Event) -> None:
        if self.start_point is None or self.rect_id is None:
            return
        x1, y1 = self.start_point
        x2, y2 = int(event.x), int(event.y)
        self.canvas.coords(self.rect_id, x1, y1, x2, y2)
        if self.size_id is not None:
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            self.canvas.coords(self.size_id, min(x1, x2) + 10, min(y1, y2) + 10)
            self.canvas.itemconfigure(self.size_id, text=f"{width} x {height}")

    def _finish_drag(self, event: tk.Event) -> None:
        if self.start_point is None:
            return
        x1, y1 = self.start_point
        x2, y2 = int(event.x), int(event.y)
        left = self.screen_region.left + min(x1, x2)
        top = self.screen_region.top + min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width < 100 or height < 100:
            messagebox.showerror("화면 영역", "선택한 영역이 너무 작습니다.")
            self.start_point = None
            return
        self.region = auto.Region(left=left, top=top, width=width, height=height)
        self.window.destroy()


def main() -> None:
    auto.enable_dpi_awareness()
    root = tk.Tk()
    app = TaskBarHeroGui(root)
    if "--start" in sys.argv:
        root.after(300, app.start_loop)
    elif "--once" in sys.argv:
        root.after(300, app.run_once)
    root.mainloop()


if __name__ == "__main__":
    main()
