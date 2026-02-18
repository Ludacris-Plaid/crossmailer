# CrossMailer

## Project Overview

**CrossMailer** is a Python-based desktop application designed for managing and executing email campaigns. It features a graphical user interface (GUI) built with **PyQt5** that allows users to manage SMTP servers, schedule campaigns with warm-up capabilities, and organize email templates.

**Key Features:**
*   **SMTP Management:** Supports multiple SMTP servers with rotation logic. Credentials are encrypted and stored locally.
*   **Campaign Control:** Start/stop capabilities with configurable sending rates (emails/hour).
*   **Warm-up Scheduler:** Automated warm-up stages (exponential ramp-up) to gradually increase sending volume.
*   **Template Library:** Manage email templates (Text/HTML) and support for placeholders.
*   **Secure Storage:** Uses AES-256 encryption (via `cryptography`) for storing sensitive SMTP passwords, protected by a master passphrase.
*   **Real-time Monitoring:** Live status panel showing campaign progress, active server, and error logs.

## Building and Running

### Prerequisites
*   Python 3.x
*   Virtual Environment (recommended)

### Installation

1.  **Clone/Navigate** to the project directory.
2.  **Set up Virtual Environment** (if not already active):
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate   # Windows
    ```
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

To launch the CrossMailer control panel:

```bash
python run_crossmailer.py
```

*Note: On startup, you will be prompted to enter a **Master Passphrase**. This key is used to decrypt your stored SMTP credentials. You must provide the same passphrase used when adding servers to access them again.*

### Headless / Server Mode

For a headless (no-GUI) runner suitable for servers:

```bash
export CROSSMAILER_PASS="your-passphrase"
export CROSSMAILER_OLLAMA_MODEL="spamqueen:latest"
python run_crossmailer_headless.py --template /path/to/template.html --rate 200 --from you@yourdomain.com --domain yourdomain.com --ai-autopilot
```

Notes:
* `--ai-autopilot` enables the LLM supervisor loop that can stop campaigns, disable failing servers, and adjust send rate.
* Tracking binds to `127.0.0.1:5000` by default; override with `CROSSMAILER_TRACK_HOST` / `CROSSMAILER_TRACK_PORT`.
* If you expose tracking publicly, set `CROSSMAILER_TRACK_TOKEN` and ensure your templates include the generated open-pixel token.

## Project Structure & Architecture

The project follows a modular structure, separating the UI, logic, and data management.

*   **`run_crossmailer.py`**: The application entry point. Initializes the PyQt application and main window.
*   **`ui/`**: Contains the GUI implementation.
    *   `main_window.py`: The core application window, handling layout, user inputs, and signal connections.
    *   `status_panel.py`: A custom widget for displaying live logs and stats.
*   **`engine/`**: Core campaign logic.
    *   `mailer.py`: Handles the actual composition and sending of emails using `aiosmtplib`.
*   **`smtp_manager/`**:
    *   `manager.py`: Manages the SQLite database (`data/smtp_credentials.db`) for storing server details and rotation logic based on health scores.
*   **`scheduler/`**:
    *   `warmup.py`: Implements the warm-up logic, gradually increasing sending rates through defined stages.
*   **`security/`**:
    *   `crypto.py`: Helper module for AES encryption/decryption of passwords.
*   **`data/`**: Stores the SQLite database (`smtp_credentials.db`).
*   **`resources/`**: Contains UI assets like `style.qss`.

## Development Conventions

*   **Dependencies:** Managed via `requirements.txt`.
*   **UI Framework:** PyQt5. All UI modifications should be done within the `ui/` module.
*   **Concurrency:** Uses `asyncio` (via `aiosmtplib`) for network operations and threading for the scheduler to keep the UI responsive.
*   **Data Persistence:** SQLite is used for local storage of configuration and credentials.
*   **Security:** Never store plain-text passwords. Always use the `SMTPManager` which delegates to `CryptoHelper`.
