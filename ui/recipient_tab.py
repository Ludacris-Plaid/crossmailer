from PyQt5 import QtWidgets, QtCore
from engine.recipient_manager import RecipientManager
from engine.validation_worker import ValidationWorker

class RecipientTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.mgr = RecipientManager()
        self.validator = None
        self.default_sequence_id = None
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # --- Top Controls ---
        top_layout = QtWidgets.QHBoxLayout()
        
        self.btn_import = QtWidgets.QPushButton("Import")
        self.btn_import.clicked.connect(self._import_file)
        
        self.btn_validate = QtWidgets.QPushButton("Validate All")
        self.btn_validate.clicked.connect(self._start_validation)
        
        self.btn_clear = QtWidgets.QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_data)
        
        self.combo_filter = QtWidgets.QComboBox()
        self.combo_filter.addItem("All")
        self.combo_filter.currentTextChanged.connect(self._refresh_table)

        top_layout.addWidget(self.btn_import)
        top_layout.addWidget(self.btn_validate)
        top_layout.addWidget(self.btn_clear)
        top_layout.addStretch()
        top_layout.addWidget(QtWidgets.QLabel("Filter:"))
        top_layout.addWidget(self.combo_filter)
        
        layout.addLayout(top_layout)

        # --- Table ---
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Email", "Provider", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # --- Stats / Progress ---
        stats_layout = QtWidgets.QHBoxLayout()
        self.lbl_stats = QtWidgets.QLabel("Total: 0 | Valid: 0 | Invalid: 0")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        
        stats_layout.addWidget(self.lbl_stats)
        stats_layout.addWidget(self.progress_bar)
        layout.addLayout(stats_layout)

        # Initial Load
        self._refresh_providers()
        self._refresh_table()

    def _import_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Emails", "", "Email Lists (*.txt *.csv);;Text Files (*.txt);;CSV Files (*.csv)"
        )
        if path:
            count = self.mgr.import_any(path, default_sequence_id=self.default_sequence_id)
            QtWidgets.QMessageBox.information(self, "Import", f"Imported {count} emails.")
            self._refresh_providers()
            self._refresh_table()

    def _clear_data(self):
        if QtWidgets.QMessageBox.question(self, "Confirm", "Delete all recipients?") == QtWidgets.QMessageBox.Yes:
            self.mgr.clear_all()
            self._refresh_table()

    def _start_validation(self):
        self.btn_validate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.validator = ValidationWorker(self.mgr)
        self.validator.progress.connect(self._update_progress)
        self.validator.finished.connect(self._validation_done)
        self.validator.start()

    def _update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _validation_done(self):
        self.btn_validate.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._refresh_table()
        QtWidgets.QMessageBox.information(self, "Done", "Validation Complete")

    def _refresh_providers(self):
        current = self.combo_filter.currentText()
        self.combo_filter.blockSignals(True)
        self.combo_filter.clear()
        self.combo_filter.addItem("All")
        for p in self.mgr.get_providers():
            self.combo_filter.addItem(p)
        
        # Restore selection if possible
        idx = self.combo_filter.findText(current)
        if idx >= 0:
            self.combo_filter.setCurrentIndex(idx)
        self.combo_filter.blockSignals(False)

    def _refresh_table(self):
        # 1. Update Table
        provider = self.combo_filter.currentText()
        rows = self.mgr.get_recipients(provider)
        
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows)) # Optimize: Set count first
        
        # Disable sorting while populating to avoid huge lags with 10k rows
        self.table.setSortingEnabled(False)
        
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(row['email']))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(row['provider']))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(row['status']))
            
        self.table.setSortingEnabled(True)

        # 2. Update Stats
        stats = self.mgr.get_stats()
        # stats is like {'Valid': 100, 'Pending': 50}
        total = sum(stats.values())
        valid = stats.get('Valid', 0)
        invalid = stats.get('Invalid Syntax', 0) + stats.get('Invalid Domain', 0)
        self.lbl_stats.setText(f"Total: {total} | Valid: {valid} | Invalid: {invalid}")
