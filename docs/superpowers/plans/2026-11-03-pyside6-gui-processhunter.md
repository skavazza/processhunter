# PySide6 ProcessHunter GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modular, test-driven PySide6 desktop application for Windows that manages target processes, kills them on-demand or via a background sentinel loop, minimizes to system tray, and supports autostart with Windows.

**Architecture:** Layered clean architecture separating pure Python OS/process business logic (`core/`) from Qt UI (`ui/`) and background threads (`ui/workers.py`), tested independently with `pytest` using mocks for Windows registry and `psutil`.

**Tech Stack:** Python 3.13, PySide6 (Qt 6), psutil, pytest

**Spec:** [docs/superpowers/specs/2026-11-03-pyside6-gui-processhunter-design.md](file:///c:/Scripts/processhunter/docs/superpowers/specs/2026-11-03-pyside6-gui-processhunter-design.md)

## Global Constraints

- Platform: Windows (10/11)
- Python Version: Python 3.13+
- No administrator elevation required for normal operation (uses `HKCU` registry for autostart)
- Process name matching must be case-insensitive and ignore trailing `.exe`
- Process termination failures (e.g. `AccessDenied`) must be caught and reported gracefully without crashing

## Review Focus

1. Process terminates while `psutil` is inspecting it (`NoSuchProcess` race condition) -> treat as successfully terminated / already gone, no exception raised.
2. Target process run by elevated/system user -> `psutil.AccessDenied` captured, reported in UI log with advisory message, other targets continue to be processed.
3. Multiple rapid launches of ProcessHunter -> second instance detects `QLockFile` and exits immediately without conflicting with the running instance.
4. Corrupted `config.json` file on disk -> backs up damaged file as `config.json.bak` and loads safe defaults instead of crashing on startup.
5. Windows autostart path containing spaces -> properly quoted executable and script path in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

---

### Task 1: Environment Setup & Core Dependencies

**Files:**
- Create: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: Installed packages `PySide6`, `psutil`, `pytest`

- [ ] **Step 1: Create `requirements.txt`**
  Add dependencies:
  ```text
  PySide6>=6.7.0
  psutil>=5.9.0
  pytest>=8.0.0
  ```

- [ ] **Step 2: Create `.gitignore`**
  Ignore `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.log`, `config.json`, `config.json.bak`, `.venv/`.

- [ ] **Step 3: Install dependencies**
  Run: `pip install -r requirements.txt`

- [ ] **Step 4: Verify installation**
  Run: `python -c "import PySide6; import psutil; import pytest; print('OK')"`
  Expected: "OK"

- [ ] **Step 5: Commit**
  ```bash
  git add requirements.txt .gitignore
  git commit -m "chore: setup dependencies and gitignore"
  ```

---

### Task 2: Core Configuration Manager (`core/config.py`)

**Files:**
- Create: `core/__init__.py`
- Create: `core/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `TargetItem(name: str, enabled: bool)`
  - `ConfigData(targets: list[TargetItem], sentinel_interval_seconds: int, autostart: bool, start_minimized: bool, minimize_to_tray_on_close: bool, notify_on_kill: bool)`
  - `ConfigManager(config_path: Path | None = None)`
    - `load() -> ConfigData`
    - `save() -> None`
    - `add_target(name: str) -> bool`
    - `remove_target(name: str) -> bool`
    - `toggle_target(name: str, enabled: bool) -> bool`
    - `set_sentinel_interval(seconds: int) -> None`

- [ ] **Step 1: Write the failing tests in `tests/test_config.py`**
  Test default creation, serialization/deserialization, duplicate target rejection, target toggle, and corrupted JSON recovery with `.bak` file.

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_config.py -v`
  Expected: FAIL (ModuleNotFoundError: No module named 'core.config')

- [ ] **Step 3: Implement `core/config.py`**
  Implement `ConfigData`, `TargetItem`, and `ConfigManager` with JSON file loading, safe fallback, and atomic write.

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_config.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add core/__init__.py core/config.py tests/__init__.py tests/test_config.py
  git commit -m "feat: implement config manager with backup and atomic persistence"
  ```

---

### Task 3: Core Hunter Engine (`core/hunter.py`)

**Files:**
- Create: `core/hunter.py`
- Create: `tests/test_hunter.py`

**Interfaces:**
- Consumes: `TargetItem` from `core.config`
- Produces:
  - `ProcessInfo(pid: int, name: str, memory_mb: float, status: str)`
  - `KillResult(pid: int, name: str, success: bool, error_message: str)`
  - `ProcessHunter`
    - `@staticmethod normalize_name(name: str) -> str`
    - `scan_active_processes() -> list[ProcessInfo]`
    - `kill_targets(target_names: list[str]) -> list[KillResult]`

- [ ] **Step 1: Write failing tests in `tests/test_hunter.py`**
  Test:
  - Name normalization (strips `.exe`, lowercases, strips whitespace)
  - Killing single and multiple matching processes with mocked `psutil.process_iter`
  - Handling `psutil.AccessDenied` gracefully
  - Handling `psutil.NoSuchProcess` without error

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_hunter.py -v`
  Expected: FAIL

- [ ] **Step 3: Implement `core/hunter.py`**
  Implement `ProcessHunter` using `psutil.process_iter` with attributes `['pid', 'name', 'memory_info', 'status']` and error handling.

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_hunter.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add core/hunter.py tests/test_hunter.py
  git commit -m "feat: implement process hunter engine with psutil"
  ```

---

### Task 4: Windows Autostart Manager (`core/autostart.py`)

**Files:**
- Create: `core/autostart.py`
- Create: `tests/test_autostart.py`

**Interfaces:**
- Produces:
  - `WindowsAutostart(app_name: str = "ProcessHunter")`
    - `is_enabled() -> bool`
    - `enable(entrypoint_path: str, python_exe: str | None = None, start_minimized: bool = True) -> bool`
    - `disable() -> bool`

- [ ] **Step 1: Write failing tests in `tests/test_autostart.py`**
  Mock `winreg` functions (`OpenKey`, `QueryValueEx`, `SetValueEx`, `DeleteValue`) to verify registry entry creation with quoted paths, `--minimized` flag, and removal.

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_autostart.py -v`
  Expected: FAIL

- [ ] **Step 3: Implement `core/autostart.py`**
  Implement `WindowsAutostart` accessing `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_autostart.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add core/autostart.py tests/test_autostart.py
  git commit -m "feat: implement windows registry autostart manager"
  ```

---

### Task 5: Logging System & Signals (`core/logger.py`)

**Files:**
- Create: `core/logger.py`
- Create: `tests/test_logger.py`

**Interfaces:**
- Produces:
  - `LogEvent(timestamp: str, level: str, message: str)`
  - `setup_app_logger(log_file: Path | None = None) -> tuple[logging.Logger, QtLogHandler]`

- [ ] **Step 1: Write failing tests in `tests/test_logger.py`**
  Verify file log formatting, rotating handler initialization, and event delivery to memory handler/callback.

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_logger.py -v`
  Expected: FAIL

- [ ] **Step 3: Implement `core/logger.py`**
  Implement rotating file log handler and custom PySide6-compatible signal/queue log emitter.

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_logger.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add core/logger.py tests/test_logger.py
  git commit -m "feat: implement logging system with rotating file and UI emitter"
  ```

---

### Task 6: UI Background Workers (`ui/workers.py`)

**Files:**
- Create: `ui/__init__.py`
- Create: `ui/workers.py`

**Interfaces:**
- Consumes: `ProcessHunter` from `core.hunter`, `ConfigManager` from `core.config`
- Produces:
  - `SentinelWorker(QThread)`:
    - Signals: `hunt_completed(list[KillResult])`, `status_changed(bool)`, `log_message(str, str)`
    - Methods: `stop()`, `set_interval(seconds: int)`
  - `ProcessScannerWorker(QThread)`:
    - Signals: `scan_completed(list[ProcessInfo])`, `scan_failed(str)`

- [ ] **Step 1: Implement `ui/workers.py`**
  Create workers subclassing `QThread` with graceful `QMutex` / stopping condition.

- [ ] **Step 2: Write test for worker lifecycle in `tests/test_workers.py`**
  Verify thread starts, emits completion signal upon single scan, and terminates cleanly when `stop()` is called.

- [ ] **Step 3: Run worker tests**
  Run: `pytest tests/test_workers.py -v`
  Expected: PASS

- [ ] **Step 4: Commit**
  ```bash
  git add ui/__init__.py ui/workers.py tests/test_workers.py
  git commit -m "feat: implement SentinelWorker and ProcessScannerWorker QThreads"
  ```

---

### Task 7: UI Components (Process Table & Target List)

**Files:**
- Create: `ui/components/__init__.py`
- Create: `ui/components/process_table.py`
- Create: `ui/components/target_list.py`

**Interfaces:**
- Produces:
  - `ProcessTableWidget(QWidget)`: Search filter bar, sortable `QTableWidget` (PID, Name, RAM MB), button `Adicionar aos Alvos`. Signal: `add_target_requested(str)`.
  - `TargetListWidget(QWidget)`: Add input bar, `QListWidget`/`QTableWidget` with checkboxes for enabled status, active count badge, delete button. Signals: `target_added(str)`, `target_removed(str)`, `target_toggled(str, bool)`.

- [ ] **Step 1: Implement `ui/components/process_table.py`**
  Build table with live filtering on text changes and column sorting.

- [ ] **Step 2: Implement `ui/components/target_list.py`**
  Build list with custom row widget displaying checkbox, process name, running status, and delete action.

- [ ] **Step 3: Verification**
  Run quick GUI component smoke script to ensure widgets instantiate without error.

- [ ] **Step 4: Commit**
  ```bash
  git add ui/components/
  git commit -m "feat: implement process table and target list UI components"
  ```

---

### Task 8: System Tray Integration (`ui/tray.py`)

**Files:**
- Create: `ui/tray.py`

**Interfaces:**
- Produces:
  - `HunterTrayIcon(QSystemTrayIcon)`:
    - Signals: `restore_requested()`, `hunt_now_requested()`, `toggle_sentinel_requested()`, `exit_requested()`
    - Methods: `update_status(is_sentinel_active: bool)`, `notify_kill(results: list[KillResult])`

- [ ] **Step 1: Implement `ui/tray.py`**
  Create `HunterTrayIcon` with generated icon pixmap, context menu actions, and double-click to restore window.

- [ ] **Step 2: Verify tray functionality**
  Verify tray actions trigger corresponding signals.

- [ ] **Step 3: Commit**
  ```bash
  git add ui/tray.py
  git commit -m "feat: implement system tray icon and notifications"
  ```

---

### Task 9: Main Window Assembly & Interconnection (`ui/main_window.py`)

**Files:**
- Create: `ui/main_window.py`

**Interfaces:**
- Consumes: `ConfigManager`, `ProcessHunter`, `WindowsAutostart`, `SentinelWorker`, `ProcessScannerWorker`, `HunterTrayIcon`, `ProcessTableWidget`, `TargetListWidget`
- Produces: `MainWindow(QMainWindow)`

- [ ] **Step 1: Implement `ui/main_window.py`**
  Assemble top control bar (Status badge, Caçar Agora, Ativar Sentinela), central split layout (Targets & Running Processes), bottom console log and settings bar (`Iniciar com o Windows`, interval spinbox).
  Connect all signals, handle `closeEvent` (minimize to tray if enabled).

- [ ] **Step 2: Verify signal flow and window instantiation**
  Smoke test initializing `MainWindow` in test environment.

- [ ] **Step 3: Commit**
  ```bash
  git add ui/main_window.py
  git commit -m "feat: assemble MainWindow with responsive layout and worker signals"
  ```

---

### Task 10: Application Entry Point & Single Instance (`app.py`)

**Files:**
- Create: `app.py`
- Create: `README.md`

**Interfaces:**
- Command-line arguments: `--minimized`
- Uses `QLockFile` for single-instance enforcement.

- [ ] **Step 1: Implement `app.py`**
  Setup `QApplication`, handle `QLockFile`, parse `--minimized`, attach `HunterTrayIcon` and `MainWindow`.

- [ ] **Step 2: Create `README.md`**
  Documentation of features, requirements, installation, and usage instructions in Portuguese.

- [ ] **Step 3: Run end-to-end test suite**
  Run: `pytest -v`
  Expected: ALL TESTS PASS

- [ ] **Step 4: Commit**
  ```bash
  git add app.py README.md
  git commit -m "feat: implement app entrypoint, single instance lock, and documentation"
  ```
