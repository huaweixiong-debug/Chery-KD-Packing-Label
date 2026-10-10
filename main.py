# -*- coding: utf-8 -*-
"""
奇瑞 KD 装箱标签二维码生成器
Chery KD Packing Label QR Code Generator
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox

try:
    import qrcode
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except ImportError as exc:
    print("缺少依赖，请先执行: pip install -r requirements.txt")
    print(f"详情: {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
COUNTERS_FILE = DATA_DIR / "counters.json"
EMPLOYEES_FILE = BASE_DIR / "employees.txt"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Parts table (客户件号 | 零件名称 | 纸箱唯一码前缀 | 纸箱编号 | 包装收容数)
# ---------------------------------------------------------------------------
PARTS: List[Dict[str, Any]] = [
    {
        "part_no": "30100351AA",
        "name": "电池冷却器",
        "unique_prefix": "A0001",
        "box_no": "ZX680540230",
        "qty": 6,
    },
    {
        "part_no": "301003472AA",
        "name": "HVAC总成智能组件",
        "unique_prefix": "B0001",
        "box_no": "ZX725680560",
        "qty": 1,
    },
    {
        "part_no": "301003484AA",
        "name": "蒸发器到压缩机管路总成",
        "unique_prefix": "C0001",
        "box_no": "ZX680540230",
        "qty": 30,
    },
    {
        "part_no": "301003483AA",
        "name": "冷凝器到蒸发器管路总成",
        "unique_prefix": "D0001",
        "box_no": "ZX1080680560",
        "qty": 10,
    },
    {
        "part_no": "301002052AA",
        "name": "过冷式冷凝器总成",
        "unique_prefix": "E0001",
        "box_no": "ZX1080680560",
        "qty": 6,
    },
    {
        "part_no": "301002053AA",
        "name": "冷凝器-压缩机管路总成",
        "unique_prefix": "F0001",
        "box_no": "ZX680540230",
        "qty": 30,
    },
    {
        "part_no": "301003471AA",
        "name": "HVAC总成模式分配箱总成",
        "unique_prefix": "G0001",
        "box_no": "ZX1080680560",
        "qty": 1,
    },
    {
        "part_no": "301003630AA",
        "name": "热管理控制模块",
        "unique_prefix": "H0001",
        "box_no": "ZX340270230",
        "qty": 20,
    },
    {
        "part_no": "301005156AA",
        "name": "电池冷却器",
        "unique_prefix": "R0001",
        "box_no": "ZX680540230",
        "qty": 12,
    },
    {
        "part_no": "FJ310004",
        "name": "单管夹",
        "unique_prefix": "J0001",
        "box_no": "ZX340270160",
        "qty": 120,
    },
]

SUPPLIER_CODE = "8KN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_employees() -> List[str]:
    """Load operator names from employees.txt (one name per line)."""
    if not EMPLOYEES_FILE.exists():
        defaults = ["张三", "李四", "王五", "赵六"]
        EMPLOYEES_FILE.write_text("\n".join(defaults) + "\n", encoding="utf-8")
        return defaults
    lines = EMPLOYEES_FILE.read_text(encoding="utf-8").splitlines()
    names = [ln.strip() for ln in lines if ln.strip()]
    return names or ["张三", "李四", "王五"]


def load_counters() -> Dict[str, int]:
    """Load last-used numeric counters keyed by letter prefix (e.g. 'A' -> 1)."""
    if not COUNTERS_FILE.exists():
        return {}
    try:
        data = json.loads(COUNTERS_FILE.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def save_counters(counters: Dict[str, int]) -> None:
    COUNTERS_FILE.write_text(
        json.dumps(counters, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_unique_code(code: str) -> Tuple[str, int, int]:
    """
    Parse unique code like A0001 into (letter_prefix, number, digit_width).
    Returns ('A', 1, 4) for 'A0001'.
    """
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", code.strip())
    if not m:
        raise ValueError(f"纸箱唯一码格式无效: {code!r}（期望如 A0001）")
    letter = m.group(1).upper()
    digits = m.group(2)
    return letter, int(digits), len(digits)


def format_unique_code(letter: str, number: int, width: int) -> str:
    return f"{letter.upper()}{number:0{width}d}"


def next_unique_code(start_code: str, counters: Dict[str, int]) -> str:
    """
    Given table prefix (e.g. A0001), return the next unused code.
    Counters store the last USED number for each letter prefix.
    On first use of prefix A with start A0001, if counter absent, use 1 (A0001).
    After generating A0001, counter['A']=1, next is A0002.
    """
    letter, start_num, width = parse_unique_code(start_code)
    last = counters.get(letter)
    if last is None:
        next_num = start_num
    else:
        next_num = max(last + 1, start_num)
    return format_unique_code(letter, next_num, width)


def commit_unique_code(code: str, counters: Dict[str, int]) -> None:
    """Record that `code` has been used."""
    letter, number, _ = parse_unique_code(code)
    counters[letter] = max(counters.get(letter, 0), number)
    save_counters(counters)


def build_qr_payload(
    part_no: str,
    qty: str,
    batch: str,
    layers: str,
    prod_date: str,
    unique_code: str,
    box_no: str,
) -> str:
    """
    Build QR string with fixed red-prefix pattern.
    Spaces after each '$' match the technical notice example.
    Letters UPPERCASE.
    """
    part_no = part_no.strip().upper()
    qty = str(qty).strip()
    batch = batch.strip().upper()
    layers = str(layers).strip()
    prod_date = prod_date.strip()
    unique_code = unique_code.strip().upper()
    box_no = box_no.strip().upper()

    return (
        f"10#{part_no}$ "
        f"11#{SUPPLIER_CODE}$ "
        f"17#{qty}$ "
        f"18#{batch}$ "
        f"19#{layers}$ "
        f"20#{prod_date}$ "
        f"31#{unique_code}$ "
        f"PK#{box_no}$"
    )


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def find_cjk_font(size: int = 14) -> ImageFont.ImageFont:
    """Try common CJK fonts on Windows / Linux / macOS."""
    candidates = [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_qr_image(payload: str, box_size: int = 8) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def make_label_preview(
    part_no: str,
    part_name: str,
    qty: str,
    batch: str,
    layers: str,
    prod_date: str,
    unique_code: str,
    qr_img: Image.Image,
) -> Image.Image:
    """
    Screen preview approximating 100×70 mm label with ~20×20 mm QR.
    At 96 dpi: 100mm≈378px, 70mm≈265px; QR 20mm≈76px — we scale up for readability.
    """
    # Use comfortable screen size (~2.5x physical px)
    W, H = 560, 390
    label = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(label)
    font_title = find_cjk_font(18)
    font_body = find_cjk_font(14)
    font_small = find_cjk_font(12)

    # Border
    draw.rectangle([2, 2, W - 3, H - 3], outline="black", width=2)

    # Left text area
    x0, y = 16, 14
    lines = [
        ("供应商代码", SUPPLIER_CODE),
        ("零件号", part_no),
        ("零件名称", part_name),
        ("数量", str(qty)),
        ("供货批次", batch),
        ("码放层数", str(layers)),
        ("生产日期", prod_date),
        ("包装箱唯一号", unique_code),
    ]
    draw.text((x0, y), "装箱标签预览 (约 100×70mm)", fill="black", font=font_title)
    y += 32
    for label_name, value in lines:
        draw.text((x0, y), f"{label_name}: {value}", fill="black", font=font_body)
        y += 28

    # QR on the right (~20×20mm region scaled)
    qr_side = 150
    qr_resized = qr_img.resize((qr_side, qr_side), Image.Resampling.NEAREST)
    qx = W - qr_side - 24
    qy = 50
    label.paste(qr_resized, (qx, qy))
    draw.text((qx, qy + qr_side + 8), "二维码 ~20×20mm", fill="gray", font=font_small)

    return label


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class PackingQRApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("奇瑞 KD 装箱标签二维码生成器")
        self.geometry("980x720")
        self.minsize(860, 640)

        self.counters = load_counters()
        self.employees = load_employees()
        self.parts_by_display: Dict[str, Dict[str, Any]] = {}
        self._photo_qr: Optional[ImageTk.PhotoImage] = None
        self._photo_label: Optional[ImageTk.PhotoImage] = None
        self._current_qr_img: Optional[Image.Image] = None
        self._updating = False

        self._build_ui()
        self._on_part_changed()
        self._refresh_payload_preview()

    # -- UI construction ----------------------------------------------------
    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Part selection
        ttk.Label(left, text="选择零件").grid(row=0, column=0, sticky="w", pady=4)
        part_choices = [
            f"{p['part_no']} — {p['name']}" for p in PARTS
        ]
        for p, display in zip(PARTS, part_choices):
            self.parts_by_display[display] = p
        self.part_var = tk.StringVar(value=part_choices[0])
        part_cb = ttk.Combobox(
            left,
            textvariable=self.part_var,
            values=part_choices,
            state="readonly",
            width=42,
        )
        part_cb.grid(row=0, column=1, sticky="ew", pady=4)
        part_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_part_changed())

        # Employee
        ttk.Label(left, text="操作员工").grid(row=1, column=0, sticky="w", pady=4)
        self.employee_var = tk.StringVar(
            value=self.employees[0] if self.employees else ""
        )
        emp_cb = ttk.Combobox(
            left,
            textvariable=self.employee_var,
            values=self.employees,
            state="readonly",
            width=42,
        )
        emp_cb.grid(row=1, column=1, sticky="ew", pady=4)

        # Fields
        self.qty_var = tk.StringVar()
        self.batch_var = tk.StringVar()
        self.layers_var = tk.StringVar()
        self.date_var = tk.StringVar(value=today_yyyymmdd())
        self.unique_var = tk.StringVar()
        self.box_no_var = tk.StringVar()

        fields = [
            (2, "包装数量", self.qty_var, False),
            (3, "发运批次", self.batch_var, False),
            (4, "码放层数", self.layers_var, False),
            (5, "生产日期 (YYYYMMDD)", self.date_var, False),
            (6, "纸箱唯一码", self.unique_var, False),
            (7, "纸箱编号", self.box_no_var, True),
        ]
        for row, label, var, readonly in fields:
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(left, textvariable=var, width=44)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            if readonly:
                entry.configure(state="readonly")
            else:
                var.trace_add("write", lambda *_a: self._refresh_payload_preview())

        left.columnconfigure(1, weight=1)

        # Hint + auto-increment button
        hint = ttk.Label(
            left,
            text="提示: 纸箱唯一码可手动改；点「取下一唯一码」按前缀自动递增并防重复。",
            foreground="#555",
            wraplength=480,
        )
        hint.grid(row=8, column=0, columnspan=2, sticky="w", pady=(2, 6))

        btn_row = ttk.Frame(left)
        btn_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=6)

        ttk.Button(
            btn_row, text="取下一唯一码", command=self._assign_next_unique
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row, text="生成二维码", command=self._generate
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row, text="打开输出目录", command=self._open_output_dir
        ).pack(side=tk.LEFT)

        # Payload preview
        ttk.Label(left, text="二维码内容预览").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(10, 2)
        )
        self.payload_text = tk.Text(left, height=4, wrap=tk.WORD, font=("Consolas", 10))
        self.payload_text.grid(row=11, column=0, columnspan=2, sticky="ew")
        self.payload_text.configure(state=tk.DISABLED)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(left, textvariable=self.status_var, foreground="#006600").grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        # Right: previews
        ttk.Label(right, text="二维码预览").pack(anchor="w")
        self.qr_canvas = tk.Label(right, background="#f0f0f0", relief=tk.SUNKEN)
        self.qr_canvas.pack(fill=tk.X, pady=(2, 10))

        ttk.Label(right, text="标签预览").pack(anchor="w")
        self.label_canvas = tk.Label(right, background="#f0f0f0", relief=tk.SUNKEN)
        self.label_canvas.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

    # -- Logic --------------------------------------------------------------
    def _current_part(self) -> Dict[str, Any]:
        return self.parts_by_display[self.part_var.get()]

    def _on_part_changed(self) -> None:
        part = self._current_part()
        self._updating = True
        try:
            self.qty_var.set(str(part["qty"]))
            self.box_no_var.set(part["box_no"])
            # Prefill next unique without committing
            code = next_unique_code(part["unique_prefix"], self.counters)
            self.unique_var.set(code)
            if not self.date_var.get().strip():
                self.date_var.set(today_yyyymmdd())
        finally:
            self._updating = False
        self._refresh_payload_preview()

    def _assign_next_unique(self) -> None:
        part = self._current_part()
        code = next_unique_code(part["unique_prefix"], self.counters)
        self.unique_var.set(code)
        self.status_var.set(f"已填充下一唯一码: {code}")
        self._refresh_payload_preview()

    def _validate(self) -> Optional[str]:
        qty = self.qty_var.get().strip()
        batch = self.batch_var.get().strip()
        layers = self.layers_var.get().strip()
        date = self.date_var.get().strip()
        unique = self.unique_var.get().strip()
        box_no = self.box_no_var.get().strip()

        if not self.employee_var.get().strip():
            return "请选择操作员工"
        if not qty or not qty.isdigit() or int(qty) <= 0:
            return "包装数量须为正整数"
        if not batch:
            return "请填写发运批次"
        if not layers or not layers.isdigit() or int(layers) <= 0:
            return "码放层数须为正整数"
        if not re.fullmatch(r"\d{8}", date):
            return "生产日期须为 YYYYMMDD 八位数字"
        try:
            datetime.strptime(date, "%Y%m%d")
        except ValueError:
            return "生产日期不是有效日期"
        try:
            parse_unique_code(unique)
        except ValueError as e:
            return str(e)
        if not box_no:
            return "纸箱编号为空，请重新选择零件"
        return None

    def _current_payload(self) -> str:
        part = self._current_part()
        return build_qr_payload(
            part_no=part["part_no"],
            qty=self.qty_var.get(),
            batch=self.batch_var.get(),
            layers=self.layers_var.get(),
            prod_date=self.date_var.get(),
            unique_code=self.unique_var.get(),
            box_no=self.box_no_var.get(),
        )

    def _refresh_payload_preview(self) -> None:
        if self._updating:
            return
        payload = self._current_payload()
        self.payload_text.configure(state=tk.NORMAL)
        self.payload_text.delete("1.0", tk.END)
        self.payload_text.insert(tk.END, payload)
        self.payload_text.configure(state=tk.DISABLED)

    def _generate(self) -> None:
        err = self._validate()
        if err:
            messagebox.showwarning("校验失败", err)
            return

        part = self._current_part()
        unique = self.unique_var.get().strip().upper()
        self.unique_var.set(unique)

        payload = self._current_payload()
        qr_img = make_qr_image(payload, box_size=8)
        self._current_qr_img = qr_img

        label_img = make_label_preview(
            part_no=part["part_no"],
            part_name=part["name"],
            qty=self.qty_var.get().strip(),
            batch=self.batch_var.get().strip().upper(),
            layers=self.layers_var.get().strip(),
            prod_date=self.date_var.get().strip(),
            unique_code=unique,
            qr_img=qr_img,
        )

        # Filename
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        emp = self.employee_var.get().strip()
        safe_emp = re.sub(r'[\\/:*?"<>|]', "_", emp)
        fname = f"{part['part_no']}_{unique}_{ts}_{safe_emp}.png"
        out_path = OUTPUT_DIR / fname
        qr_img.save(out_path)

        # Also save a label preview PNG
        label_fname = f"{part['part_no']}_{unique}_{ts}_{safe_emp}_label.png"
        label_path = OUTPUT_DIR / label_fname
        label_img.save(label_path)

        # Commit counter so uniqueness survives restarts
        commit_unique_code(unique, self.counters)

        # Show on screen
        qr_show = qr_img.resize((220, 220), Image.Resampling.NEAREST)
        self._photo_qr = ImageTk.PhotoImage(qr_show)
        self.qr_canvas.configure(image=self._photo_qr)

        label_show = label_img.copy()
        label_show.thumbnail((480, 340), Image.Resampling.LANCZOS)
        self._photo_label = ImageTk.PhotoImage(label_show)
        self.label_canvas.configure(image=self._photo_label)

        # Advance unique code for convenience
        next_code = next_unique_code(part["unique_prefix"], self.counters)
        self.unique_var.set(next_code)
        self._refresh_payload_preview()

        self.status_var.set(f"已生成: {out_path.name}")
        messagebox.showinfo(
            "生成成功",
            f"二维码已保存:\n{out_path}\n\n标签预览:\n{label_path}\n\n内容:\n{payload}",
        )

    def _open_output_dir(self) -> None:
        path = str(OUTPUT_DIR)
        try:
            if sys.platform.startswith("win"):
                import os

                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["open", path])
            else:
                import subprocess

                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showinfo("输出目录", f"{path}\n\n无法自动打开: {exc}")


def main() -> None:
    app = PackingQRApp()
    app.mainloop()


if __name__ == "__main__":
    main()
