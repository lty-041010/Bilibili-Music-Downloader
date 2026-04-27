import os
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFileDialog, QTextEdit, QLabel, QFrame, QComboBox,
                             QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QTextCursor
from config import load_config, save_config
from api import get_all_favorite
from downloader import download_audio_task, single_download
import requests

class WorkerSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, str)  # 进度(0-100)、视频标题
    data_ready = pyqtSignal(list)
    finished = pyqtSignal()

class BiliMusicDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.video_list = []
        self.save_path = self.cfg.get("save_path", "")
        self.signals = WorkerSignals()
        self.signals.log.connect(self.append_log)
        self.signals.progress.connect(self.update_progress)
        self.signals.data_ready.connect(self.update_table)
        self.signals.finished.connect(self.on_load_finished)
        # 下载控制标志位
        self.download_cancel = False
        self.download_pause = False

        self.setWindowTitle("B站收藏夹音频下载器｜Ctrl/Shift选择版")
        self.resize(1100, 720)
        self.init_ui()
        self.load_cfg_to_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        cfg_frame = QFrame()
        cfg_frame.setStyleSheet("border:1px solid #ddd;border-radius:6px;padding:10px;")
        cfg_layout = QVBoxLayout(cfg_frame)
        self.edit_fid = QLineEdit()
        self.edit_fid.setPlaceholderText("收藏夹ID")
        self.edit_sess = QLineEdit()
        self.edit_sess.setPlaceholderText("SESSDATA（浏览器获取）")
        self.edit_jct = QLineEdit()
        self.edit_jct.setPlaceholderText("bili_jct（浏览器获取）")
        self.edit_bvid = QLineEdit()
        self.edit_bvid.setPlaceholderText("单个BV号（例如：BV1xx411c7mC）")
        cfg_layout.addWidget(self.edit_fid)
        cfg_layout.addWidget(self.edit_sess)
        cfg_layout.addWidget(self.edit_jct)
        cfg_layout.addWidget(self.edit_bvid)
        main_layout.addWidget(cfg_frame)

        btn_box = QHBoxLayout()
        self.btn_load = QPushButton("加载收藏夹")
        self.btn_all = QPushButton("全选")
        self.btn_rev = QPushButton("反选")
        self.btn_dir = QPushButton("选择保存目录")
        self.btn_single = QPushButton("单个BV下载")
        btn_box.addWidget(self.btn_load)
        btn_box.addWidget(self.btn_all)
        btn_box.addWidget(self.btn_rev)
        btn_box.addWidget(self.btn_dir)
        btn_box.addWidget(self.btn_single)
        main_layout.addLayout(btn_box)

        # 下载控制按钮
        control_layout = QHBoxLayout()
        self.btn_down = QPushButton("✅ 批量下载选中音频")
        self.btn_down.setStyleSheet("background:#27ae60;color:white;padding:8px;border-radius:6px;font-size:14px;")
        self.btn_pause = QPushButton("⏸️ 暂停下载")
        self.btn_pause.setStyleSheet("background:#f39c12;color:white;padding:8px;border-radius:6px;font-size:14px;")
        self.btn_cancel = QPushButton("❌ 取消下载")
        self.btn_cancel.setStyleSheet("background:#e74c3c;color:white;padding:8px;border-radius:6px;font-size:14px;")
        control_layout.addWidget(self.btn_down)
        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(control_layout)

        # 音频设置
        settings_layout = QHBoxLayout()
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["128k", "192k", "320k"])
        self.quality_combo.setCurrentText("320k")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP3", "WAV", "FLAC"])
        self.format_combo.setCurrentText("MP3")
        settings_layout.addWidget(QLabel("音质："))
        settings_layout.addWidget(self.quality_combo)
        settings_layout.addWidget(QLabel("格式："))
        settings_layout.addWidget(self.format_combo)
        settings_layout.addStretch()
        main_layout.addLayout(settings_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p% - 准备中")
        main_layout.addWidget(self.progress_bar)

        # ==================== 原生稳定版：无自定义、绝不闪退 ====================
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["BV号", "标题"])
        self.table.setColumnWidth(0, 130)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # 原生标准模式：Ctrl多选 + Shift区间选（最稳定，不闪退）
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        # 选中整行
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 禁止编辑
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 醒目高亮（蓝色底白字）
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #0078D7;
                color: white;
            }
        """)

        main_layout.addWidget(self.table)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        main_layout.addWidget(self.log_text)

        self.btn_load.clicked.connect(self.start_load_task)
        self.btn_all.clicked.connect(self.select_all)
        self.btn_rev.clicked.connect(self.reverse_select)
        self.btn_dir.clicked.connect(self.choose_save_dir)
        self.btn_down.clicked.connect(self.start_download)
        self.btn_single.clicked.connect(self.start_single_download)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel.clicked.connect(self.cancel_download)

        self.append_log("✅ 程序启动完成｜支持 Ctrl 单选 / Shift 连选")

    def load_cfg_to_ui(self):
        self.edit_fid.setText(self.cfg.get("fid", ""))
        self.edit_sess.setText(self.cfg.get("sessdata", ""))
        self.edit_jct.setText(self.cfg.get("bili_jct", ""))

    def append_log(self, msg):
        if msg.startswith("✅"):
            msg = f'<font color="green">{msg}</font>'
        elif msg.startswith("❌"):
            msg = f'<font color="red">{msg}</font>'
        elif msg.startswith("⚠️"):
            msg = f'<font color="orange">{msg}</font>'
        self.log_text.append(msg)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def save_current_cfg(self):
        self.cfg["fid"] = self.edit_fid.text().strip()
        self.cfg["sessdata"] = self.edit_sess.text().strip()
        self.cfg["bili_jct"] = self.edit_jct.text().strip()
        save_config(self.cfg)

    def start_load_task(self):
        self.save_current_cfg()
        self.btn_load.setEnabled(False)
        # 设置进度条为加载动画模式
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("加载中...")
        fid = self.edit_fid.text().strip()
        sess = self.edit_sess.text().strip()
        jct = self.edit_jct.text().strip()
        threading.Thread(target=self.load_task, args=(fid, sess, jct), daemon=True).start()

    def load_task(self, fid, sess, jct):
        if not fid or not sess:
            self.signals.log.emit("❌ 请填写收藏夹ID和SESSDATA")
            self.signals.finished.emit()
            return
        lst, msg = get_all_favorite(fid, sess, jct)
        if not lst:
            self.signals.log.emit(f"❌ 加载失败：{msg}")
        else:
            self.video_list = lst
            self.signals.data_ready.emit(lst)
            self.signals.log.emit(f"✅ 成功加载 {len(lst)} 条收藏视频")
        self.signals.finished.emit()

    def update_table(self, video_list):
        self.table.setRowCount(len(video_list))
        for idx, item in enumerate(video_list):
            self.table.setItem(idx, 0, QTableWidgetItem(item["bvid"]))
            self.table.setItem(idx, 1, QTableWidgetItem(item["title"]))

    def on_load_finished(self):
        self.btn_load.setEnabled(True)
        # 恢复进度条到正常状态
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p% - 准备中")

    def update_progress(self, progress, title):
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{progress}% - {title}")

    # ==================== 全选 ====================
    def select_all(self):
        self.table.selectAll()

    # ==================== 反选 ====================
    def reverse_select(self):
        # 获取所有行
        total = self.table.rowCount()
        # 获取当前选中行
        selected = {index.row() for index in self.table.selectedIndexes()}
        # 清空选择
        self.table.clearSelection()
        # 反选未选中的行
        for row in range(total):
            if row not in selected:
                self.table.selectRow(row)

    def choose_save_dir(self):
        p = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if p:
            self.save_path = p
            self.cfg["save_path"] = p
            save_config(self.cfg)
            self.append_log(f"📁 保存目录：{p}")

    # ==================== 获取选中行（适配新选择模式） ====================
    def start_download(self):
        # 重置下载控制标志位
        self.download_cancel = False
        self.download_pause = False
        self.btn_pause.setText("⏸️ 暂停下载")
        
        self.save_current_cfg()
        # 获取所有选中的行号（去重）
        rows = list({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            self.append_log("❌ 请选中要下载的视频")
            return
        if not self.save_path:
            self.save_path = os.path.join(os.getcwd(), "Bilibili_Music")
            os.makedirs(self.save_path, exist_ok=True)
        sess = self.edit_sess.text().strip()
        quality = self.quality_combo.currentText()
        format = self.format_combo.currentText()

        def log_cb(m):
            self.signals.log.emit(m)

        def progress_cb(progress, title):
            self.signals.progress.emit(progress, title)

        threading.Thread(target=download_audio_task, args=(self.video_list, rows, self.save_path, sess, log_cb, progress_cb, quality, format, self),
                         daemon=True).start()

    def toggle_pause(self):
        self.download_pause = not self.download_pause
        if self.download_pause:
            self.btn_pause.setText("▶️ 继续下载")
            self.append_log("⏸️ 下载已暂停")
        else:
            self.btn_pause.setText("⏸️ 暂停下载")
            self.append_log("▶️ 下载已继续")

    def cancel_download(self):
        self.download_cancel = True
        self.append_log("❌ 下载已取消")

    def start_single_download(self):
        # 重置下载控制标志位
        self.download_cancel = False
        self.download_pause = False
        self.btn_pause.setText("⏸️ 暂停下载")
        
        self.save_current_cfg()
        bvid = self.edit_bvid.text().strip()
        if not bvid:
            self.append_log("❌ 请输入BV号")
            return
        if not self.save_path:
            self.save_path = os.path.join(os.getcwd(), "Bilibili_Music")
            os.makedirs(self.save_path, exist_ok=True)
        sess = self.edit_sess.text().strip()

        def log_cb(m):
            self.signals.log.emit(m)

        def progress_cb(progress, title):
            self.signals.progress.emit(progress, title)

        # 获取视频信息
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://www.bilibili.com/video/{bvid}/",
            "Cookie": f"SESSDATA={sess}"
        }
        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        try:
            info_resp = requests.get(info_url, headers=headers, timeout=10).json()
            if info_resp["code"] == -101:
                self.append_log("❌ Cookie过期（SESSDATA无效），请重新获取")
                return
            if info_resp["code"] != 0:
                self.append_log(f"❌ 获取视频信息失败：{info_resp['message']}")
                return
            title = info_resp["data"]["title"]
            # 创建临时item对象
            item = {"title": title, "bvid": bvid}
            quality = self.quality_combo.currentText()
            format = self.format_combo.currentText()
            # 启动下载线程
            threading.Thread(target=single_download, args=(item, self.save_path, sess, log_cb, progress_cb, quality, format, self),
                             daemon=True).start()
        except Exception as e:
            self.append_log(f"❌ 获取视频信息失败：{str(e)[:50]}")
