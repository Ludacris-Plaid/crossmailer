from PyQt5 import QtWidgets, QtCore, QtGui
from engine.ai_worker import AIWorker
from engine.ai_brain import AIBrain
from .chat_widget import ChatWidget
import os # Import os for path basename

class AITab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.brain_instance = AIBrain() # Temporary instance to get defaults
        self.worker = AIWorker(self.brain_instance.model_config) # Initialize worker with default config
        self._init_ui()
        self._connect_signals()
        self._load_ui_config() # Load saved config if any
        self._check_model_status()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # --- Top: Model Configuration ---
        model_config_group = QtWidgets.QGroupBox("Model Configuration")
        model_config_layout = QtWidgets.QVBoxLayout(model_config_group)
        
        # Status Label (moved here from init)
        self.lbl_status = QtWidgets.QLabel("Model Status: Checking...")
        model_config_layout.addWidget(self.lbl_status)

        # Source Selection
        source_layout = QtWidgets.QHBoxLayout()
        source_layout.addWidget(QtWidgets.QLabel("Source:"))
        self.radio_hf = QtWidgets.QRadioButton("HuggingFace Hub")
        self.radio_local = QtWidgets.QRadioButton("Local File")
        self.radio_ollama = QtWidgets.QRadioButton("Ollama")
        source_layout.addWidget(self.radio_hf)
        source_layout.addWidget(self.radio_local)
        source_layout.addWidget(self.radio_ollama)
        source_layout.addStretch()
        model_config_layout.addLayout(source_layout)

        # HuggingFace Inputs
        hf_form = QtWidgets.QFormLayout()
        self.input_hf_repo = QtWidgets.QLineEdit()
        self.input_hf_repo.setPlaceholderText(self.brain_instance.model_config['hf_repo_id'])
        self.input_hf_file = QtWidgets.QLineEdit()
        self.input_hf_file.setPlaceholderText(self.brain_instance.model_config['hf_filename'])
        hf_form.addRow("Repo ID:", self.input_hf_repo)
        hf_form.addRow("Filename:", self.input_hf_file)
        model_config_layout.addLayout(hf_form)

        # Local File Input
        local_form = QtWidgets.QFormLayout()
        local_file_layout = QtWidgets.QHBoxLayout()
        self.input_local_path = QtWidgets.QLineEdit()
        self.btn_browse_local = QtWidgets.QPushButton("Browse...")
        local_file_layout.addWidget(self.input_local_path)
        local_file_layout.addWidget(self.btn_browse_local)
        local_form.addRow("Local Path:", local_file_layout)
        model_config_layout.addLayout(local_form)

        # Ollama Input
        ollama_form = QtWidgets.QFormLayout()
        self.input_ollama_model = QtWidgets.QLineEdit()
        self.input_ollama_model.setPlaceholderText("spamqueen:latest")
        ollama_form.addRow("Ollama Model:", self.input_ollama_model)
        model_config_layout.addLayout(ollama_form)

        self.btn_load_model = QtWidgets.QPushButton("Load/Download Model")
        model_config_layout.addWidget(self.btn_load_model)
        
        layout.addWidget(model_config_group)

        # --- Mode Tabs (Generator / Chat) ---
        self.mode_tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.mode_tabs)

        # === Generator Tab ===
        gen_tab = QtWidgets.QWidget()
        gen_layout = QtWidgets.QVBoxLayout(gen_tab)
        
        # Inputs
        inputs_group = QtWidgets.QGroupBox("Campaign Generation")
        inputs_layout = QtWidgets.QVBoxLayout(inputs_group)
        form = QtWidgets.QFormLayout()
        self.input_topic = QtWidgets.QLineEdit()
        self.input_topic.setPlaceholderText("e.g. High-end SEO services")
        
        self.input_audience = QtWidgets.QLineEdit()
        self.input_audience.setPlaceholderText("e.g. Dentists in California")
        
        self.combo_tone = QtWidgets.QComboBox()
        self.combo_tone.addItems(["Professional", "Friendly", "Direct", "Playful"])
        
        form.addRow("Campaign Topic:", self.input_topic)
        form.addRow("Target Audience:", self.input_audience)
        form.addRow("Tone:", self.combo_tone)
        inputs_layout.addLayout(form)
        self.btn_generate = QtWidgets.QPushButton("✨ Generate Campaign")
        self.btn_generate.setFixedHeight(40)
        inputs_layout.addWidget(self.btn_generate)
        gen_layout.addWidget(inputs_group)

        # Output
        output_group = QtWidgets.QGroupBox("Generated Email")
        output_layout = QtWidgets.QVBoxLayout(output_group)
        self.output_subject = QtWidgets.QLineEdit()
        self.output_subject.setPlaceholderText("Generated Subject Line")
        output_layout.addWidget(QtWidgets.QLabel("Subject:"))
        output_layout.addWidget(self.output_subject)

        self.output_body = QtWidgets.QTextEdit()
        self.output_body.setPlaceholderText("Generated HTML Body...")
        output_layout.addWidget(QtWidgets.QLabel("Email Body (HTML):"))
        output_layout.addWidget(self.output_body)
        
        self.btn_save = QtWidgets.QPushButton("Save as Template")
        output_layout.addWidget(self.btn_save)
        gen_layout.addWidget(output_group)
        
        self.mode_tabs.addTab(gen_tab, "Campaign Generator")

        # === Chat Tab ===
        self.chat_widget = ChatWidget()
        self.mode_tabs.addTab(self.chat_widget, "Chat")

    def _connect_signals(self):
        self.radio_hf.toggled.connect(self._update_model_config_ui)
        self.radio_local.toggled.connect(self._update_model_config_ui)
        self.radio_ollama.toggled.connect(self._update_model_config_ui)
        self.btn_browse_local.clicked.connect(self._browse_local_file)
        self.btn_load_model.clicked.connect(self._load_or_download_model)
        
        self.btn_generate.clicked.connect(self._start_generation)
        self.btn_save.clicked.connect(self._save_template)
        
        # Chat signals
        self.chat_widget.message_sent.connect(self._on_chat_message)
        
        # Connect worker signals
        self.worker.download_finished.connect(self._on_model_action_finished)
        self.worker.generation_finished.connect(self._on_generation_finished)
        self.worker.chat_finished.connect(self.chat_widget.append_response)
        self.worker.error_occurred.connect(self._on_error)

    def _load_ui_config(self):
        # Apply defaults to UI elements
        source = self.brain_instance.model_config.get('source', 'HuggingFace')
        if source in {"HuggingFace", "LocalFile"} and not self.brain_instance.HAS_LLAMA:
            source = "Ollama"
        if source == 'HuggingFace':
            self.radio_hf.setChecked(True)
        elif source == 'Ollama':
            self.radio_ollama.setChecked(True)
        else:
            self.radio_local.setChecked(True)
            
        self.input_hf_repo.setText(self.brain_instance.model_config.get('hf_repo_id', ''))
        self.input_hf_file.setText(self.brain_instance.model_config.get('hf_filename', ''))
        self.input_local_path.setText(self.brain_instance.model_config.get('local_path', ''))
        self.input_ollama_model.setText(self.brain_instance.model_config.get('ollama_model', 'spamqueen:latest'))
        self._update_model_config_ui() 

    def _update_model_config_ui(self):
        # Enable/disable fields based on radio button selection
        has_llama = self.brain_instance.HAS_LLAMA
        is_hf = self.radio_hf.isChecked()
        is_local = self.radio_local.isChecked()
        is_ollama = self.radio_ollama.isChecked()
        self.radio_hf.setEnabled(has_llama)
        self.radio_local.setEnabled(has_llama)
        if not has_llama and (is_hf or is_local):
            self.radio_ollama.setChecked(True)
            is_hf = False
            is_local = False
            is_ollama = True
        
        self.input_hf_repo.setEnabled(is_hf)
        self.input_hf_file.setEnabled(is_hf)
        self.input_local_path.setEnabled(is_local)
        self.btn_browse_local.setEnabled(is_local)
        self.input_ollama_model.setEnabled(is_ollama)
        
        if is_hf:
            self.btn_load_model.setText("Download Model")
        elif is_ollama:
            self.btn_load_model.setText("Use Ollama Model")
        else:
            self.btn_load_model.setText("Load Local Model")
        
        self._check_model_status()

    def _browse_local_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select LLM Model File", "", "LLM Files (*.gguf *.llm)")
        if path:
            self.input_local_path.setText(path)
            self._check_model_status()

    def _get_current_model_config(self):
        source = 'HuggingFace'
        if self.radio_local.isChecked(): source = 'LocalFile'
        if self.radio_ollama.isChecked(): source = 'Ollama'
        
        config = {
            'source': source,
            'hf_repo_id': self.input_hf_repo.text().strip(),
            'hf_filename': self.input_hf_file.text().strip(),
            'local_path': self.input_local_path.text().strip(),
            'ollama_model': self.input_ollama_model.text().strip()
        }
        return config

    def _check_model_status(self):
        config = self._get_current_model_config()
        if config['source'] == 'Ollama':
             self.lbl_status.setText(f"Model Status: ✅ Assume Ollama Ready ({config['ollama_model']})")
             self.btn_generate.setEnabled(True)
             self.btn_load_model.setEnabled(True)
             return

        temp_brain = AIBrain(config) 
        
        if temp_brain.is_model_downloaded():
            self.lbl_status.setText(f"Model Status: ✅ Ready ({os.path.basename(temp_brain._get_current_model_path())})")
            self.btn_load_model.setText("Model Loaded (Re-load/Download)")
            self.btn_generate.setEnabled(True)
        else:
            if config['source'] == 'HuggingFace' and config['hf_repo_id'] and config['hf_filename']:
                self.lbl_status.setText("Model Status: ⬇️ Available for Download")
                self.btn_load_model.setText("Download Model")
            elif config['source'] == 'LocalFile' and config['local_path']:
                self.lbl_status.setText("Model Status: 🚫 Local File Not Found")
                self.btn_load_model.setText("Load Local Model")
            else:
                self.lbl_status.setText("Model Status: ⚠️ Incomplete Config")
                self.btn_load_model.setText("Load/Download Model")
            self.btn_load_model.setEnabled(True)

    def _load_or_download_model(self):
        config = self._get_current_model_config()
        if config['source'] in {'HuggingFace', 'LocalFile'} and not self.brain_instance.HAS_LLAMA:
            self._on_error("llama-cpp-python is required for local/HF models. Install it or use Ollama.")
            return
        # Re-instantiate worker with the *new* config
        self.worker = AIWorker(config) 
        self.worker.download_finished.connect(self._on_model_action_finished)
        self.worker.generation_finished.connect(self._on_generation_finished) 
        self.worker.chat_finished.connect(self.chat_widget.append_response)
        self.worker.error_occurred.connect(self._on_error)

        self.btn_load_model.setEnabled(False)
        self.btn_generate.setEnabled(False)
        
        if config['source'] == 'HuggingFace':
            self.lbl_status.setText(f"Model Status: ⬇️ Downloading {config['hf_filename']}...")
            self.worker.download_model()
        elif config['source'] == 'LocalFile':
            self.lbl_status.setText(f"Model Status: ⏳ Loading {os.path.basename(config['local_path'])}...")
            try:
                self.worker.brain.load_model()
                self._on_model_action_finished(True)
            except Exception as e:
                self._on_error(f"Failed to load local model: {e}")
                self._on_model_action_finished(False)
        elif config['source'] == 'Ollama':
             self._on_model_action_finished(True)

    def _on_model_action_finished(self, success):
        self._check_model_status()
        if success:
             self.btn_generate.setEnabled(True)
             if self.radio_ollama.isChecked():
                  QtWidgets.QMessageBox.information(self, "Success", "Ollama config set.")
             else:
                  # Check if model was actually loaded
                  if self.worker.brain.llm is not None:
                       QtWidgets.QMessageBox.information(self, "Success", "Model loaded successfully!")
        else:
            QtWidgets.QMessageBox.critical(self, "Error", "Model action failed.")

    def _on_chat_message(self, message):
         # Ensure worker has latest config
         self.worker.brain.model_config.update(self._get_current_model_config())
         self.worker.chat(message)

    def _start_generation(self):
        topic = self.input_topic.text()
        audience = self.input_audience.text()
        if not topic or not audience:
            QtWidgets.QMessageBox.warning(self, "Missing Info", "Please enter topic and audience.")
            return

        self.btn_generate.setText("Thinking... (Generating)")
        self.btn_generate.setEnabled(False)
        
        self.worker.brain.model_config.update(self._get_current_model_config())
        self.worker.generate(topic, audience, self.combo_tone.currentText())

    def _on_generation_finished(self, result):
        self.btn_generate.setText("✨ Generate Campaign")
        self.btn_generate.setEnabled(True)
        
        self.output_subject.setText(result.get("subject", ""))
        self.output_body.setPlainText(result.get("body", ""))

    def _on_error(self, msg):
        self.btn_generate.setText("✨ Generate Campaign")
        self.btn_generate.setEnabled(True)
        self.btn_load_model.setEnabled(True)
        self.lbl_status.setText(f"Model Status: ❌ Error ({msg})")
        QtWidgets.QMessageBox.critical(self, "AI Error", msg)

    def _save_template(self):
        content = self.output_body.toPlainText()
        if not content:
            return
            
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Template", "", "HTML Files (*.html);;Text Files (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            QtWidgets.QMessageBox.information(self, "Saved", f"Template saved to {path}")
