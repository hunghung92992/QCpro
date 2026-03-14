# -*- coding: utf-8 -*-
"""
/iqc/iqc_chart_page.py
(UPDATED FLOW: Dept -> Lot -> Test -> Date)
"""

from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd

# --- PySide6 Imports ---
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem, QSplitter, QFileDialog
)

# --- Fluent UI Imports ---
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, ComboBox,
    TableWidget, CalendarPicker, FluentIcon as FIF, BodyLabel,
    SubtitleLabel, InfoBar, IndeterminateProgressBar
)

# --- Matplotlib ---
import matplotlib

matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

# --- App Core ---
from app.services.department_service import DepartmentService
from app.services.catalog_service import CatalogService
from app.services.iqc_service import IQCService
from app.services.iqc_rule_service import IQCRuleService
from app.utils.validators import to_float_safe as _to_float


# --- Helpers ---
def _map_semi_text_to_y(text: str) -> float:
    t = str(text).lower().strip()
    mapping = {
        'neg': 0.0, 'negative': 0.0, 'âm tính': 0.0, '-': 0.0, 'norm': 0.0, '0': 0.0,
        'trace': 1.0, 'tr': 1.0, 'vết': 1.0, '+-': 1.0, '±': 1.0, '0.15': 1.0,
        '1+': 2.0, '+1': 2.0, 'pos': 2.0, 'dương': 2.0,
        '2+': 3.0, '+2': 3.0,
        '3+': 4.0, '+3': 4.0,
        '4+': 5.0, '+4': 5.0,
        '5+': 6.0, '+5': 6.0
    }
    for k, v in mapping.items():
        if t == k: return v
    try:
        return float(t)
    except:
        return 0.0


SEMI_DISPLAY_MAP = {0.0: "Neg", 1.0: "Trace", 2.0: "1+", 3.0: "2+", 4.0: "3+", 5.0: "4+", 6.0: "5+"}


# ============================================================================
# WORKER THREAD
# ============================================================================
class ChartDataWorker(QThread):
    data_ready = Signal(dict, list)  # levels_data, master_dates
    error_occurred = Signal(str)

    def __init__(self, service_pack: dict, params: dict):
        super().__init__()
        self.iqc = service_pack['iqc']
        self.catalog = service_pack['catalog']
        self.rule = service_pack['rule']
        self.params = params

    def run(self):
        try:
            dep = self.params['dep']
            test = self.params['test']
            f_d = self.params['f_d']
            t_d = self.params['t_d']
            lots = self.params['lots']  # List of tuples (level_str, lot_no, color)

            # 1. Xác định Run Type từ history hoặc catalog
            # (Lấy mẫu 1 dòng để biết quant/semi/qual)
            sample = self.iqc.get_history(department=dep, test_code=test, limit=1)
            run_type = (sample[0].get("run_type", "quant") or "quant").lower() if sample else "quant"
            is_quant = (run_type == "quant")

            levels_data = {}
            all_dates = set()

            for level_str, lot, color in lots:
                if not lot: continue

                # Fetch Data
                history = self.iqc.get_history(
                    department=dep, run_date_from=f_d, run_date_to=t_d,
                    test_code=test, level=level_str, lot_no=lot,
                    limit=300, sort_order="ASC", active_only=True
                )

                valid_rows = []
                raw_values = []

                # Trong hàm run() của ChartDataWorker:
                for r in history:
                    # 🌟 THAY ĐỔI: Lấy Z-Score và Rule đã tính sẵn từ DB
                    z_val = _to_float(r.get('z_score'))
                    violation = r.get('violation_rule')  # Mã lỗi: 1_3s, 2_2s...

                    val = _to_float(r.get('value_num'))  # Giá trị thực tế để tính Stats

                    if val is not None:
                        try:
                            d_str = r['run_time'].split(" ")[0]
                            r['_date_str'] = d_str
                            r['_plot_z'] = z_val  # Lưu Z-score để vẽ
                            r['_violation'] = violation
                            valid_rows.append(r)
                            raw_values.append(val)
                            all_dates.add(d_str)
                        except:
                            pass

                if not valid_rows: continue

                # Get Target
                tgt = self.catalog.get_target_by_lot(test, level_str, lot) or {}
                t_mean = _to_float(tgt.get('mean'))
                t_sd = _to_float(tgt.get('sd'))
                t_tea = _to_float(tgt.get('tea'))

                if not is_quant:
                    t_txt = tgt.get('reference_range') or ""
                    t_mean = _map_semi_text_to_y(t_txt) if run_type == 'semi' else (
                        1.0 if 'POS' in t_txt.upper() else 0.0)

                # Stats Calculation
                stats = {
                    "N": len(raw_values),
                    "Mean": np.mean(raw_values) if raw_values else 0,
                    "SD": np.std(raw_values, ddof=1) if len(raw_values) > 1 else 0,
                    "Target": t_mean,
                    "TargetSD": t_sd,
                    "TEa": t_tea
                }
                if stats["Mean"] and stats["Mean"] != 0:
                    stats["CV"] = (stats["SD"] / stats["Mean"]) * 100
                else:
                    stats["CV"] = 0

                stats["Sigma"] = 0
                if t_tea and stats["CV"] > 0 and t_mean:
                    bias = abs(stats["Mean"] - t_mean)
                    bias_pct = (bias / t_mean) * 100
                    stats["Sigma"] = (t_tea - bias_pct) / stats["CV"]

                levels_data[level_str] = {
                    "rows": valid_rows,
                    "target": {"mean": t_mean, "sd": t_sd},
                    "lot": lot,
                    "color": color,
                    "stats": stats,
                    "run_type": run_type
                }

            self.data_ready.emit(levels_data, sorted(list(all_dates)))

        except Exception as e:
            self.error_occurred.emit(str(e))


# ============================================================================
# CHART WIDGET
# ============================================================================
class LJChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(figsize=(8, 6), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.hide()

        self.layout.addWidget(self.canvas)

        self.canvas.mpl_connect('button_press_event', self._on_plot_clicked)
        self._click_callback = None
        self._current_data_map = {}

    def set_callback(self, func):
        self._click_callback = func

    def _on_plot_clicked(self, event):
        if event.button == 3 and self._click_callback and event.xdata is not None:
            idx = int(round(event.xdata))
            found_rec = None
            for key, rec in self._current_data_map.items():
                if key[0] == idx:
                    found_rec = rec
                    break
            if found_rec: self._click_callback(found_rec)

    def plot(self, levels_data: dict, master_dates: list):
        """
        Vẽ biểu đồ Levey-Jennings dựa trên dữ liệu đã được xử lý Westgard từ Backend.
        """
        self.fig.clear()
        self._current_data_map = {}

        if not levels_data:
            self.canvas.draw()
            return

        ax = self.fig.add_subplot(111)
        x_indices = range(len(master_dates))

        # Lấy mẫu thông tin từ level đầu tiên để xác định kiểu chạy (quant/semi/qual)
        first_lvl = next(iter(levels_data.values()))
        run_type = first_lvl.get('run_type', 'quant')

        # --- 1. THIẾT LẬP CÁC VÙNG CẢNH BÁO (ZONES) ---
        if run_type == "quant":
            # Đường Mean và các ngưỡng SD
            ax.axhline(0, color='#107C10', linestyle='-', linewidth=2, label='Mean', alpha=0.8)  # Mean xanh đậm
            ax.axhline(2, color='#F39C12', linestyle='--', linewidth=1, alpha=0.6)  # Ngưỡng 2SD (Vàng)
            ax.axhline(-2, color='#F39C12', linestyle='--', linewidth=1, alpha=0.6)
            ax.axhline(3, color='#C50F1F', linestyle=':', linewidth=1.2, alpha=0.7)  # Ngưỡng 3SD (Đỏ)
            ax.axhline(-3, color='#C50F1F', linestyle=':', linewidth=1.2, alpha=0.7)

            # Tô màu nền vùng vi phạm (>2SD)
            ax.fill_between(x_indices, 2, 4.5, color='#F39C12', alpha=0.05)
            ax.fill_between(x_indices, -4.5, -2, color='#F39C12', alpha=0.05)

            ax.set_ylabel("Chỉ số SDI (Z-Score)", fontweight='bold')
            ax.set_ylim(-4.5, 4.5)
        elif run_type == "semi":
            ax.set_yticks(list(SEMI_DISPLAY_MAP.keys()))
            ax.set_yticklabels(list(SEMI_DISPLAY_MAP.values()), fontsize=8)
            ax.grid(True, axis='y', linestyle='--', alpha=0.3)
            ax.set_ylabel("Mức độ (Semi-Quant)", fontweight='bold')
        else:
            ax.set_yticks([0, 1])
            ax.set_yticklabels(["Âm (0)", "Dương (1)"])
            ax.set_ylabel("Kết quả Định tính", fontweight='bold')

        # --- 2. VẼ ĐƯỜNG DỮ LIỆU VÀ DÁN NHÃN LỖI ---
        for lvl_key, data in levels_data.items():
            rows = data['rows']
            color = data['color']
            lot_no = data['lot']

            # Tạo map để tra cứu nhanh dữ liệu theo ngày
            date_rec_map = {r['_date_str']: r for r in rows}

            plot_vals = []
            for i, d_str in enumerate(master_dates):
                rec = date_rec_map.get(d_str)
                if rec:
                    self._current_data_map[(i, lvl_key)] = rec

                    # 🌟 LẤY DỮ LIỆU TỪ BACKEND
                    # Nếu là định lượng, vẽ theo Z-Score đã tính sẵn (_plot_z)
                    # Nếu là định tính/bán định lượng, vẽ theo giá trị đã map (_plot_val)
                    val = rec.get('_plot_z') if run_type == "quant" else rec.get('_plot_val')
                    plot_vals.append(val)

                    # 🌟 DÁN NHÃN LỖI WESTGARD (Annotate)
                    vio = rec.get('_violation')
                    if vio and vio != "OK" and run_type == "quant":
                        # Chỉ hiện nhãn nếu có lỗi vi phạm
                        ax.annotate(
                            vio.replace('_', '-'),  # VD: "1_3s" thành "1-3s"
                            (i, val),
                            textcoords="offset points",
                            xytext=(0, 12),  # Đẩy chữ lên trên điểm 12 pixels
                            ha='center',
                            fontsize=8,
                            fontweight='bold',
                            color=color,  # Màu chữ khớp với màu đường của Level đó
                            bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.7, ec='none')
                        )
                else:
                    plot_vals.append(None)

            # Vẽ đường nối và các điểm tròn
            ax.plot(x_indices, plot_vals, marker='o', markersize=6, linestyle='-',
                    color=color, label=f"{lvl_key} (Lot: {lot_no})", alpha=0.8, linewidth=1.5)

            # Đánh dấu X đỏ cho các điểm vi phạm cực nặng (>3SD)
            if run_type == "quant":
                for idx, v in enumerate(plot_vals):
                    if v is not None and abs(v) > 3:
                        ax.plot(idx, v, marker='x', color='red', markersize=10, markeredgewidth=2)

        # --- 3. HOÀN THIỆN GIAO DIỆN ---
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3, frameon=False, fontsize=9)
        ax.grid(True, axis='x', linestyle=':', alpha=0.4)

        if master_dates:
            # Tự động tính khoảng cách nhãn trục X để không bị khít nhau
            step = max(1, len(master_dates) // 12)
            ax.set_xticks(x_indices[::step])
            display_labels = []
            for d in master_dates[::step]:
                try:
                    display_labels.append(dt.datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m"))
                except:
                    display_labels.append(d)
            ax.set_xticklabels(display_labels, rotation=30, fontsize=8)

        self.fig.tight_layout()
        self.canvas.draw()


# ============================================================================
# MAIN PAGE: IQCChartPage
# ============================================================================
class IQCChartPage(QWidget):
    def __init__(self, parent=None, db_path=None, **kwargs):
        super().__init__(parent)

        self.iqc_service = IQCService()
        self.catalog_service = CatalogService()
        self.dept_service = DepartmentService()
        self.rule_service = IQCRuleService()

        self._init_ui()
        self._load_departments()
        self._current_stats_data = []

        # Biến cờ để tránh trigger loop khi load dữ liệu
        self._loading = False

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- 1. FILTER CARD ---
        filter_card = CardWidget(self)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(15, 15, 15, 15)
        fl.setSpacing(15)

        self.cb_dep = ComboBox()
        self.cb_dep.setPlaceholderText("Chọn Khoa")
        self.cb_test = ComboBox()
        self.cb_test.setPlaceholderText("Chọn Xét nghiệm")

        self.ed_from = CalendarPicker()
        self.ed_from.setDateFormat(Qt.ISODate)
        self.ed_from.setDate(QDate.currentDate().addMonths(-1))

        self.ed_to = CalendarPicker()
        self.ed_to.setDateFormat(Qt.ISODate)
        self.ed_to.setDate(QDate.currentDate())

        self.btn_draw = PrimaryPushButton(FIF.CHEVRON_RIGHT, "Vẽ Biểu Đồ")
        self.btn_draw.clicked.connect(self._start_drawing)

        self.btn_export = PushButton(FIF.SAVE, "Xuất Excel")
        self.btn_export.clicked.connect(self._export_excel)

        def add_field(label, widget):
            v = QVBoxLayout()
            v.setSpacing(5)
            v.addWidget(BodyLabel(label))
            v.addWidget(widget)
            fl.addLayout(v)

        # [CẬP NHẬT UI] 1. Khoa
        add_field("1. Khoa:", self.cb_dep)

        # [CẬP NHẬT UI] 2. LOT (Đưa lên trước Test)
        v_lots = QVBoxLayout()
        v_lots.setSpacing(5)
        v_lots.addWidget(BodyLabel("2. Chọn LOT:"))
        h_lots = QHBoxLayout()
        self.cb_l1 = ComboBox();
        self.cb_l1.setPlaceholderText("Lot L1")
        self.cb_l2 = ComboBox();
        self.cb_l2.setPlaceholderText("Lot L2")
        self.cb_l3 = ComboBox();
        self.cb_l3.setPlaceholderText("Lot L3")

        # Kết nối sự kiện khi chọn Lot để load Test
        self.cb_l1.currentIndexChanged.connect(self._on_lot_changed)
        self.cb_l2.currentIndexChanged.connect(self._on_lot_changed)
        self.cb_l3.currentIndexChanged.connect(self._on_lot_changed)

        h_lots.addWidget(self.cb_l1)
        h_lots.addWidget(self.cb_l2)
        h_lots.addWidget(self.cb_l3)
        v_lots.addLayout(h_lots)
        fl.addLayout(v_lots)

        # [CẬP NHẬT UI] 3. Xét nghiệm (Sau khi chọn Lot)
        add_field("3. Xét nghiệm:", self.cb_test)

        # [CẬP NHẬT UI] 4. Thời gian
        add_field("Từ ngày:", self.ed_from)
        add_field("Đến ngày:", self.ed_to)

        fl.addStretch(1)
        v_btns = QVBoxLayout()
        v_btns.addStretch(1)
        v_btns.addWidget(self.btn_draw)
        v_btns.addWidget(self.btn_export)
        fl.addLayout(v_btns)

        layout.addWidget(filter_card)

        # --- 2. REST OF UI ---
        self.progress = IndeterminateProgressBar(self)
        self.progress.hide()
        layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Vertical)
        self.chart_view = LJChartWidget()
        self.chart_view.set_callback(self._on_point_clicked)
        chart_container = CardWidget()
        cl = QVBoxLayout(chart_container)
        cl.addWidget(self.chart_view)
        splitter.addWidget(chart_container)

        self.tbl_stats = TableWidget()
        self.tbl_stats.setColumnCount(10)
        self.tbl_stats.setHorizontalHeaderLabels(
            ["Level", "Lot", "N", "Mean", "SD", "CV%", "Target", "Sigma", "Đánh giá", "Hành động"])
        self.tbl_stats.verticalHeader().hide()
        self.tbl_stats.setBorderVisible(True)

        stats_container = CardWidget()
        sl = QVBoxLayout(stats_container)
        sl.addWidget(SubtitleLabel("Bảng Thống kê", self))
        sl.addWidget(self.tbl_stats)
        splitter.addWidget(stats_container)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.cb_dep.currentIndexChanged.connect(self._on_dep_changed)

    # --- LOGIC MỚI ---
    def _load_departments(self):
        self._loading = True
        self.cb_dep.clear()
        deps = self.dept_service.list_departments(active_only=True)
        for d in deps:
            self.cb_dep.addItem(d.name, userData=d.id)
        self._loading = False
        self._on_dep_changed()

    def _on_dep_changed(self):
        """
        [FLOW 1] Chọn Khoa -> Load danh sách LOT (L1, L2, L3) của khoa đó.
        """
        if self._loading: return
        dep = self.cb_dep.currentText()
        if not dep: return

        self._loading = True

        # Clear dữ liệu cũ
        self.cb_test.clear()
        for cb in [self.cb_l1, self.cb_l2, self.cb_l3]: cb.clear()

        # Load LOTs của khoa
        lots_data = self.catalog_service.list_active_lots_by_level(dep)

        for k, cb in zip(['L1', 'L2', 'L3'], [self.cb_l1, self.cb_l2, self.cb_l3]):
            cb.addItem("", None)
            for l in lots_data.get(k, []):
                # Lưu ID của Lot vào userData để sau này tìm Test
                cb.addItem(l['lot_no'], userData=l.get('id'))

            # Tự động chọn Lot mới nhất nếu có
            if cb.count() > 1: cb.setCurrentIndex(1)

        self._loading = False

        # Sau khi load Lot xong -> Trigger load Test
        self._on_lot_changed()

    def _on_lot_changed(self):
        """
        [FLOW 2] Chọn LOT -> Tìm các Xét nghiệm có trong các Lot đó.
        """
        if self._loading: return

        # Lấy ID của các Lot đang chọn
        lot_ids = []
        for cb in [self.cb_l1, self.cb_l2, self.cb_l3]:
            lid = cb.currentData()  # userData chứa lot_id
            if lid: lot_ids.append(lid)

        if not lot_ids:
            self.cb_test.clear()
            return

        self._loading = True
        current_test = self.cb_test.currentText()  # Giữ lại selection nếu có
        self.cb_test.clear()

        # Tìm tất cả Test Code trong các Lot đã chọn
        # Logic: Lấy danh sách Test của từng Lot rồi gộp lại (Union)
        found_tests = set()

        for lid in lot_ids:
            details = self.catalog_service.get_details_by_lot(lid)
            for d in details:
                if d.get('test_code'):
                    found_tests.add(d['test_code'])

        # Hiển thị ra ComboBox Test
        sorted_tests = sorted(list(found_tests))
        self.cb_test.addItems(sorted_tests)

        # Khôi phục selection nếu test đó vẫn còn trong danh sách
        if current_test in sorted_tests:
            self.cb_test.setCurrentText(current_test)
        elif self.cb_test.count() > 0:
            self.cb_test.setCurrentIndex(0)

        self._loading = False

    def _start_drawing(self):
        test = self.cb_test.currentText()
        if not test:
            InfoBar.warning("Thiếu thông tin", "Vui lòng chọn Xét nghiệm.", parent=self)
            return

        self.progress.show()
        self.progress.start()
        self.btn_draw.setEnabled(False)
        self.tbl_stats.setRowCount(0)
        self.chart_view.plot({}, [])

        params = {
            "dep": self.cb_dep.currentText(),
            "test": test,
            "f_d": self.ed_from.date.toString("yyyy-MM-dd"),
            "t_d": self.ed_to.date.toString("yyyy-MM-dd"),
            "lots": [
                ("L1", self.cb_l1.currentText(), "#0078D4"),
                ("L2", self.cb_l2.currentText(), "#E67E22"),
                ("L3", self.cb_l3.currentText(), "#27AE60")
            ]
        }

        service_pack = {
            "iqc": self.iqc_service,
            "catalog": self.catalog_service,
            "rule": self.rule_service
        }

        self.worker = ChartDataWorker(service_pack, params)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_data_ready(self, levels_data, master_dates):
        self.chart_view.plot(levels_data, master_dates)

        self.tbl_stats.setRowCount(0)
        self._current_stats_data = []

        for lvl, data in levels_data.items():
            stats = data['stats']
            row = self.tbl_stats.rowCount()
            self.tbl_stats.insertRow(row)

            def item(val, fmt="{:.2f}"):
                if val is None or val == 0: return QTableWidgetItem("—")
                return QTableWidgetItem(fmt.format(val))

            self.tbl_stats.setItem(row, 0, QTableWidgetItem(lvl))
            self.tbl_stats.setItem(row, 1, QTableWidgetItem(data['lot']))
            self.tbl_stats.setItem(row, 2, QTableWidgetItem(str(stats['N'])))
            self.tbl_stats.setItem(row, 3, item(stats['Mean']))
            self.tbl_stats.setItem(row, 4, item(stats['SD']))
            self.tbl_stats.setItem(row, 5, item(stats['CV'], "{:.2f}%"))
            self.tbl_stats.setItem(row, 6, item(stats['Target']))

            sigma_item = item(stats['Sigma'])
            if stats['Sigma'] >= 6:
                sigma_item.setBackground(QColor("#C8E6C9"))
            elif stats['Sigma'] > 0 and stats['Sigma'] < 3:
                sigma_item.setBackground(QColor("#FFCDD2"))
            self.tbl_stats.setItem(row, 7, sigma_item)

            eval_txt = "Tốt" if stats['Sigma'] >= 6 else ("Kém" if stats['Sigma'] > 0 and stats['Sigma'] < 3 else "Đạt")
            if stats['N'] == 0: eval_txt = ""
            self.tbl_stats.setItem(row, 8, QTableWidgetItem(eval_txt))

            stats['Level'] = lvl
            stats['Lot'] = data['lot']
            self._current_stats_data.append(stats)

    def _on_worker_finished(self):
        self.progress.stop()
        self.progress.hide()
        self.btn_draw.setEnabled(True)

    def _on_error(self, msg):
        InfoBar.error("Lỗi", msg, parent=self)

    def _on_point_clicked(self, record):
        InfoBar.info("Chi tiết",
                     f"ID: {record.get('id')}\nKết quả: {record.get('value_num')}\nNgày: {record.get('run_time')}",
                     parent=self)

    def _export_excel(self):
        if not self._current_stats_data:
            InfoBar.warning("Lỗi", "Chưa có dữ liệu để xuất.", parent=self)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu Excel", "IQC_Stats.xlsx", "Excel Files (*.xlsx)")
        if path:
            try:
                df = pd.DataFrame(self._current_stats_data)
                df.to_excel(path, index=False)
                InfoBar.success("Thành công", f"Đã lưu tại {path}", parent=self)
            except Exception as e:
                InfoBar.error("Lỗi lưu file", str(e), parent=self)