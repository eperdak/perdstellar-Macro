import os
import time
import json
import webbrowser
import psutil
import configparser
import customtkinter
import logging
import sys
import ctypes
import threading
import queue
from ctypes import wintypes
import re
import requests
import pyautogui
import win32gui
import win32process
from datetime import datetime, timezone
from PIL import Image


# logging and exception handling

logging.basicConfig(
    filename='crash.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('biomemacro')

def exception_handler(exc_type, exc_value, exc_tb):
    logger.exception(f"Uncaught exception: {exc_value}")
    ctypes.windll.user32.MessageBoxW(0, "Check crash.log for crash details.", "Crashed!", 0)
    sys.exit(1)

sys.excepthook = exception_handler


def _signal_launcher_ready():
    event_name = os.environ.get('PERDSTALLAR_READY_EVENT')
    if not event_name:
        return

    try:
        kernel32 = ctypes.windll.kernel32
        open_event = kernel32.OpenEventW
        open_event.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        open_event.restype = ctypes.c_void_p

        set_event = kernel32.SetEvent
        set_event.argtypes = [ctypes.c_void_p]
        set_event.restype = ctypes.c_int

        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int

        handle = open_event(0x0002, 0, event_name)
        if handle:
            try:
                set_event(handle)
            finally:
                close_handle(handle)
    except Exception:
        pass


def _asset_path(filename):
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, 'assets', filename)


class BiomeTracker:

    def __init__(self):
            try:
                myappid = 'perdstellar.biomemacro.app.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

            customtkinter.set_default_color_theme("dark-blue")
            self.root = customtkinter.CTk()
            self.root.title("perdstellar's Macro")
            self.root.geometry('505x285')
            self.root.resizable(False, False)

            icon_path = _asset_path('icon.ico')
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(default=icon_path)
                except Exception as e:
                    print(f"[UI] Icon set error: {e}")

            self.logs_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'Roblox', 'logs')
            self.current_biome = "NORMAL"
            self.last_position = 0
            self.detection_running = False
            self.detection_thread = None
            self.biome_callback = None
            self.log_file_path = None
            self.current_log_timestamp = None
            self.lock = threading.Lock()

            self.biome_data = self._load_biome_data()

    def _load_biome_data(self):
        url = "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/assets/biomes_data.json"

        default_data = {
            "NORMAL": {"color": "0xffffff", "thumbnail_url": ""},
            "WINDY": {"color": "0x9ae5ff", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/WINDY.png"},
            "RAINY": {"color": "0x027cbd", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/RAINY.png"},
            "SNOWY": {"color": "0xDceff9", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/SNOWY.png"},
            "SAND STORM": {"color": "0x8F7057", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/SAND%20STORM.png"},
            "HELL": {"color": "0xff4719", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/HELL.png"},
            "STARFALL": {"color": "0x011ab7", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/STARFALL.png"},
            "CORRUPTION": {"color": "0x6d32a8", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/CORRUPTION.png"},
            "NULL": {"color": "0x838383", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/NULL.png"},
            "GLITCHED": {"color": "0xbfff00", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/GLITCHED.png"},
            "DREAMSPACE": {"color": "0xea9dda", "thumbnail_url": "https://maxstellar.github.io/biome_thumb/DREAMSPACE.png"},
            "CYBERSPACE": {"color": "0x0A1A3D", "thumbnail_url": "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/images/CYBERSPACE.png"},
            "EGGLAND": {"color": "0xd4fc8d", "thumbnail_url": "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/images/EGGLAND.png"},
            "BLAZING SUN": {"color": "0xFFDEAD", "thumbnail_url": ""},
            "INCINERATOR": {"color": "0xCD853F", "thumbnail_url": ""}
        }

        try:
            r = requests.get(url, timeout=3)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data:
                print("[BiomeTracker] Loaded biome data from GitHub")
                return data
        except Exception as e:
            print(f"[BiomeTracker] Failed to load from GitHub, using defaults: {e}")

        return default_data

    def set_biome_callback(self, callback):
        self.biome_callback = callback

    def _parse_log_timestamp(self, filename):
        """
        Parse log filename to extract timestamp
        Format: 0.736.0.7361348_20260907T203326Z_Player_77795_last.log
        Returns: timestamp string (20260907T203326Z) or None
        """
        try:
            parts = filename.split('_')
            if len(parts) >= 2:
                timestamp = parts[1]
                return timestamp
        except Exception:
            pass
        return None

    def _has_biome_data(self, log_file_path):
        """Check if log file contains BloxstrapRPC biome data"""
        try:
            if not os.path.exists(log_file_path):
                return False

            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if '[BloxstrapRPC]' in line and '"largeImage"' in line:
                        return True
            return False
        except Exception:
            return False


    def _get_latest_log_file(self):
        if not os.path.exists(self.logs_dir):
            return None

        try:
            files = [f for f in os.listdir(self.logs_dir)
                     if f.endswith('.log') and 'Installer' not in f]

            if not files:
                return None

            # parse and sort by timestamp in filename
            log_files_with_timestamps = []
            for filename in files:
                timestamp = self._parse_log_timestamp(filename)
                if timestamp:
                    full_path = os.path.join(self.logs_dir, filename)
                    # skip small files(likely launcher logs, not the game logs)
                    # game logs are typically larger than 9999 bytes
                    try: 
                        file_size = os.path.getsize(full_path)
                        if file_size <= 9999: # 9999 bytes or less = launcher log
                            continue 
                    except:
                        pass
                    log_files_with_timestamps.append((timestamp, full_path, filename))

            if not log_files_with_timestamps:
                # fallback to modification time if no timestamps found
                files_full = [os.path.join(self.logs_dir, f) for f in files]
                return max(files_full, key=os.path.getmtime)

            # sort by timestamp (newest first)
            log_files_with_timestamps.sort(key=lambda x: x[0], reverse=True)
            latest_timestamp, latest_file, latest_filename = log_files_with_timestamps[0]

            # if we haven't tracked a log yet, use the latest one
            if self.current_log_timestamp is None:
                self.current_log_timestamp = latest_timestamp
                print(f"[BiomeTracker] Tracking new log: {latest_filename}")
                return latest_file

            # if latest log is newer than current, switch to it immediately
            if latest_timestamp > self.current_log_timestamp:
                print(f"[BiomeTracker] Switching to newer log: {latest_filename}")
                self.current_log_timestamp = latest_timestamp
                return latest_file

            # otherwise, keep using current log
            if self.log_file_path and os.path.exists(self.log_file_path):
                return self.log_file_path

            # if current log doesn't exist anymore, use latest
            self.current_log_timestamp = latest_timestamp
            return latest_file

        except Exception as e:
            print(f"[BiomeTracker] Error finding log file: {e}")
            return None

    def _read_log_file(self, log_file_path):
        if not os.path.exists(log_file_path):
            return []

        # reset position if file changed
        if self.log_file_path != log_file_path:
            print(f"[BiomeTracker] Log file changed, resetting position: {os.path.basename(log_file_path)}")
            self.log_file_path = log_file_path
            self.last_position = 0

        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                file.seek(self.last_position)
                lines = file.readlines()
                new_position = file.tell()

                if lines:
                    print(f"[BiomeTracker] Read {len(lines)} new lines from log (pos: {self.last_position} -> {new_position})")

                self.last_position = new_position
                return lines
        except Exception as e:
            print(f"[BiomeTracker] Error reading log: {e}")
            return []

    def _check_biome_in_logs(self, log_file_path):
        log_lines = self._read_log_file(log_file_path)

        if not log_lines:
            return

        biome_changes = []
        for line in log_lines:
            if '[BloxstrapRPC]' in line and '"largeImage"' in line:
                match = re.search(r'"largeImage"\s*:\s*\{[^}]*"hoverText"\s*:\s*"([^"]+)"', line)
                if match:
                    biome = match.group(1).strip().upper()
                    biome_changes.append(biome)

        if not biome_changes:
            return

        # only process the last biome change from this batch
        latest_biome = biome_changes[-1]

        # add unknown biomes to data
        if latest_biome not in self.biome_data and latest_biome != "NORMAL":
            print(f"[BiomeTracker] New biome detected: {latest_biome}")
            self.biome_data[latest_biome] = {
                "color": "0xffffff",
                "thumbnail_url": "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/images/biome_placeholder.png"
            }

        if latest_biome != self.current_biome:
            with self.lock:
                old_biome = self.current_biome
                self.current_biome = latest_biome

            print(f"[BiomeTracker] Biome changed: {old_biome} -> {latest_biome}")

            # trigger callback
            if self.biome_callback:
                try:
                    threading.Thread(
                        target=self.biome_callback,
                        args=(latest_biome, old_biome),
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"[BiomeTracker] Callback error: {e}")

    def _detection_loop(self):
        while self.detection_running:
            try:
                current_log_file = self._get_latest_log_file()

                if current_log_file:
                    self._check_biome_in_logs(current_log_file)

                time.sleep(1)
            except Exception as e:
                print(f"[BiomeTracker] Detection loop error: {e}")
                time.sleep(2)

    def start_detection(self):
        if self.detection_running:
            return

        self.detection_running = True
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True, name="BiomeDetection")
        self.detection_thread.start()
        print("[BiomeTracker] Detection started")

    def stop_detection(self):
        self.detection_running = False
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=3)
        print("[BiomeTracker] Detection stopped")


class _GlobalHotkeyListener:
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_NOREPEAT = 0x4000
    HOTKEYS = {
        1: (0x70, "start"),
        2: (0x71, "stop"),
        3: (0x72, "pause"),
    }

    def __init__(self, commands):
        self.commands = commands
        self.available = False
        self.error = None
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._stop_requested = threading.Event()
        self._lock = threading.Lock()

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._register_hotkey = self._user32.RegisterHotKey
        self._register_hotkey.argtypes = [wintypes.HWND, wintypes.INT, wintypes.UINT, wintypes.UINT]
        self._register_hotkey.restype = wintypes.BOOL

        self._unregister_hotkey = self._user32.UnregisterHotKey
        self._unregister_hotkey.argtypes = [wintypes.HWND, wintypes.INT]
        self._unregister_hotkey.restype = wintypes.BOOL

        self._get_message = self._user32.GetMessageW
        self._get_message.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self._get_message.restype = wintypes.BOOL

        self._post_thread_message = self._user32.PostThreadMessageW
        self._post_thread_message.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._post_thread_message.restype = wintypes.BOOL

        self._get_current_thread_id = self._kernel32.GetCurrentThreadId
        self._get_current_thread_id.argtypes = []
        self._get_current_thread_id.restype = wintypes.DWORD

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.available

            self.available = False
            self.error = None
            self._thread_id = 0
            self._ready.clear()
            self._stopped.clear()
            self._stop_requested.clear()
            self._thread = threading.Thread(target=self._listen, daemon=True, name="GlobalHotkeys")
            self._thread.start()

        if not self._ready.wait(timeout=3):
            self.error = "Timed out while registering global hotkeys."
            self.stop()
            return False

        return self.available

    def stop(self):
        self._stop_requested.set()

        with self._lock:
            thread = self._thread
            thread_id = self._thread_id

        if thread_id:
            self._post_thread_message(thread_id, self.WM_QUIT, 0, 0)

        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)

    def _listen(self):
        registered_ids = []

        try:
            with self._lock:
                self._thread_id = self._get_current_thread_id()

            for hotkey_id, (virtual_key, _) in self.HOTKEYS.items():
                if self._stop_requested.is_set():
                    return

                if not self._register_hotkey(None, hotkey_id, self.MOD_NOREPEAT, virtual_key):
                    error_code = ctypes.get_last_error()
                    self.error = f"F{hotkey_id} is already used by another application (Windows error {error_code})."
                    return

                registered_ids.append(hotkey_id)

            self.available = True
            self._ready.set()

            message = wintypes.MSG()
            while True:
                result = self._get_message(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break

                if message.message == self.WM_HOTKEY:
                    command = self.HOTKEYS.get(int(message.wParam))
                    if command:
                        self.commands.put(command[1])
        except Exception as error:
            self.error = f"Could not register global hotkeys: {error}"
        finally:
            for hotkey_id in registered_ids:
                self._unregister_hotkey(None, hotkey_id)

            with self._lock:
                self.available = False
                self._thread_id = 0

            self._ready.set()
            self._stopped.set()


class BiomeMacroApp:

    RARE_BIOMES = ["GLITCHED", "DREAMSPACE", "CYBERSPACE"]

    def __init__(self):
        customtkinter.set_default_color_theme("dark-blue")
        self.root = customtkinter.CTk()
        self.root.title("perdstellar's Macro")
        self.root.geometry('498x300')
        self.root.resizable(False, False)

        icon_path = _asset_path('icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass

        self.started = False
        self.paused = False
        self.destroyed = False
        self._hotkey_commands = queue.Queue()
        self._global_hotkeys = _GlobalHotkeyListener(self._hotkey_commands)
        self._hotkey_dispatch_after_id = None

        self.config_name = 'config.ini'
        self.config = self._load_config()

        self.tracker = BiomeTracker()
        self.tracker.set_biome_callback(self.on_biome_change)

        self.webhook_urls = self._parse_webhook_urls()

        self.biome_vars = {}
        self._init_biome_vars()

        self.anti_afk_enabled = customtkinter.BooleanVar(self.root, value=self.config.getboolean('Macro', 'anti_afk', fallback=True))
        self.anti_afk_interval = customtkinter.StringVar(self.root, value=self.config.get('Macro', 'anti_afk_interval', fallback='5'))
        self.anti_afk_thread = None
        self.anti_afk_running = False

        self.roblox_monitor_enabled = customtkinter.BooleanVar(self.root, value=self.config.getboolean('Macro', 'roblox_monitor', fallback=True))
        self.roblox_monitor_thread = None
        self.roblox_monitor_running = False
        self.roblox_window_handle = None

        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._schedule_hotkey_dispatch()

    def _load_config(self):
        config = configparser.ConfigParser()

        if not os.path.exists(self.config_name):
            config['Webhook'] = {
                'webhook_url': "",
                'private_server': "",
                'discord_user_id': ""
            }
            config['Biomes'] = {
                'windy': "Message",
                'snowy': "Message",
                'rainy': "Message",
                'sand_storm': "Message",
                'hell': "Message",
                'starfall': "Message",
                'corruption': "Message",
                'null': "Message"
            }
            config['Macro'] = {
                'anti_afk': "True",
                'anti_afk_interval': "5",
                'roblox_monitor': "True"
            }

            with open(self.config_name, 'w') as f:
                config.write(f)
            print("[Config] Created default config.ini")

        config.read(self.config_name)
        return config

    def _parse_webhook_urls(self):
        raw = self.config.get('Webhook', 'webhook_url', fallback="")
        if not raw:
            return []

        if raw.startswith('['):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [u.strip() for u in parsed if u and isinstance(u, str)]
            except:
                pass

        return [raw.strip()] if raw.strip() else []

    def _init_biome_vars(self):
        for biome_key in ['windy', 'snowy', 'rainy', 'sand_storm', 'hell', 'starfall', 'corruption', 'null']:
            value = self.config.get('Biomes', biome_key, fallback="Message")
            self.biome_vars[biome_key] = customtkinter.StringVar(self.root, value)

    def _build_ui(self):
        # Configure grid layout
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self.tabview = customtkinter.CTkTabview(self.root, width=505, height=230, command=self._on_tab_change)
        self.tabview.grid(row=0, column=0, sticky='nsew', columnspan=75, padx=10, pady=(0, 0))
        self.tabview.add("Webhook")
        self.tabview.add("Macro")
        self.tabview.add("Credits")
        self.tabview._segmented_button.configure(font=customtkinter.CTkFont(family="Segoe UI", size=16))
        self.tabview._segmented_button.grid(sticky="w", padx=15)

        self._build_webhook_tab(self.tabview.tab("Webhook"))

        self._build_macro_tab(self.tabview.tab("Macro"))

        self._build_credits_tab(self.tabview.tab("Credits"))

        self._build_control_buttons()

        self.tabview.set("Webhook")
        self._adjust_window_size("Webhook")

    def _on_tab_change(self):
        current_tab = self.tabview.get()
        self._adjust_window_size(current_tab)

    def _adjust_window_size(self, tab_name):
        if tab_name == "Webhook":
            self.root.geometry('498x300')
        elif tab_name == "Macro":
            self.root.geometry('498x335')
        elif tab_name == "Credits":
            self.root.geometry('498x335')

    def _build_webhook_tab(self, parent):
        # Configure parent to center content vertically
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_rowconfigure(2, weight=1)

        # Create centered frame
        center_frame = customtkinter.CTkFrame(parent, fg_color="transparent")
        center_frame.grid(row=1, column=0, sticky="ew")

        # Webhook URL
        webhook_label = customtkinter.CTkLabel(center_frame, text="Webhook URL:",
                                               font=customtkinter.CTkFont(family="Segoe UI", size=20))
        webhook_label.grid(column=0, row=0, columnspan=2, padx=(10, 0), pady=(0, 0), sticky="w")

        self.webhook_field = customtkinter.CTkEntry(center_frame,
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                    width=319)
        webhook_value = self.config.get('Webhook', 'webhook_url', fallback="")
        if webhook_value:
            self.webhook_field.insert(0, webhook_value)
        self.webhook_field.grid(row=0, column=1, padx=(144, 0), pady=(5, 0), sticky="w")

        # Private Server
        ps_label = customtkinter.CTkLabel(center_frame, text="Private Server URL:",
                                         font=customtkinter.CTkFont(family="Segoe UI", size=20))
        ps_label.grid(column=0, row=1, padx=(10, 0), pady=(15, 0), columnspan=2, sticky="w")

        self.ps_field = customtkinter.CTkEntry(center_frame,
                                              font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                              width=285)
        ps_value = self.config.get('Webhook', 'private_server', fallback="")
        if ps_value:
            self.ps_field.insert(0, ps_value)
        self.ps_field.grid(row=1, column=1, padx=(179, 0), pady=(18, 0), sticky="w")

        # Discord User ID
        discid_label = customtkinter.CTkLabel(center_frame, text="Discord User ID:",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20))
        discid_label.grid(column=0, row=2, padx=(10, 0), pady=(15, 0), columnspan=2, sticky="w")

        self.discid_field = customtkinter.CTkEntry(center_frame,
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                   width=309)
        discid_value = self.config.get('Webhook', 'discord_user_id', fallback="")
        if discid_value:
            self.discid_field.insert(0, discid_value)
        self.discid_field.grid(row=2, column=1, padx=(155, 0), pady=(18, 0), sticky="w")

    def _build_macro_tab(self, parent):
        biome_button = customtkinter.CTkButton(parent, text="Configure Pings",
                                              font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                              width=200,
                                              command=self.open_configure_pings)
        biome_button.grid(row=0, column=0, padx=(10, 0), pady=(12, 0), sticky="w")

        anti_afk_toggle = customtkinter.CTkCheckBox(parent, text="Anti-AFK",
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=18),
                                                    variable=self.anti_afk_enabled,
                                                    command=self._save_anti_afk_settings)
        anti_afk_toggle.grid(row=1, column=0, padx=(10, 0), pady=(15, 0), sticky="w")

        interval_label = customtkinter.CTkLabel(parent, text="Interval (minutes):",
                                               font=customtkinter.CTkFont(family="Segoe UI", size=16))
        interval_label.grid(row=2, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

        self.anti_afk_interval_entry = customtkinter.CTkEntry(parent,
                                                              font=customtkinter.CTkFont(family="Segoe UI", size=16),
                                                              width=150,
                                                              textvariable=self.anti_afk_interval)
        self.anti_afk_interval_entry.grid(row=2, column=0, padx=(160, 0), pady=(10, 0), sticky="w")
        self.anti_afk_interval_entry.bind("<FocusOut>", lambda e: self._save_anti_afk_settings())

        roblox_monitor_toggle = customtkinter.CTkCheckBox(parent, text="Stop the macro on Roblox crash",
                                                          font=customtkinter.CTkFont(family="Segoe UI", size=18),
                                                          variable=self.roblox_monitor_enabled,
                                                          command=self._save_roblox_monitor_settings)
        roblox_monitor_toggle.grid(row=3, column=0, padx=(10, 0), pady=(15, 0), sticky="w")

        info_label = customtkinter.CTkLabel(parent,
                                           text="Anti-AFK will jump in-game to prevent disconnect",
                                           font=customtkinter.CTkFont(family="Segoe UI", size=12))
        info_label.grid(row=4, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

    def _build_credits_tab(self, parent):
        try:
            perd_pfp_path = _asset_path("perd.png")
            if os.path.exists(perd_pfp_path):
                perd_pfp = customtkinter.CTkImage(dark_image=Image.open(perd_pfp_path), size=(60, 60))
                perd_pfp_label = customtkinter.CTkLabel(parent, image=perd_pfp, text="")
                perd_pfp_label.grid(row=0, column=0, padx=(10, 0), pady=(10, 0), sticky="w")
                perd_pfp_label.image = perd_pfp
        except:
            pass

        credits_frame_1 = customtkinter.CTkFrame(parent)
        credits_frame_1.grid(row=0, column=1, padx=(7, 0), pady=(10, 0), sticky="w")

        eperdak_label = customtkinter.CTkLabel(credits_frame_1, text="eperdak - Refactored & Maintained",
                                              font=customtkinter.CTkFont(family="Segoe UI", size=14, weight="bold"))
        eperdak_label.grid(row=0, column=0, padx=(5, 0), sticky="nw")

        github_link = customtkinter.CTkLabel(credits_frame_1, text="GitHub",
                                            font=("Segoe UI", 12, "underline"),
                                            text_color="dodgerblue", cursor="hand2")
        github_link.grid(row=1, column=0, padx=(5, 0), sticky="nw")
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/eperdak"))

        try:
            max_pfp_path = _asset_path("maxstellar.png")
            if os.path.exists(max_pfp_path):
                max_pfp = customtkinter.CTkImage(dark_image=Image.open(max_pfp_path), size=(60, 60))
                max_pfp_label = customtkinter.CTkLabel(parent, image=max_pfp, text="")
                max_pfp_label.grid(row=1, column=0, padx=(10, 0), pady=(5, 0), sticky="w")
                max_pfp_label.image = max_pfp
        except:
            pass

        credits_frame_2 = customtkinter.CTkFrame(parent)
        credits_frame_2.grid(row=1, column=1, padx=(7, 0), pady=(5, 0), sticky="w")

        max_label = customtkinter.CTkLabel(credits_frame_2, text="maxstellar - Original Creator",
                                          font=customtkinter.CTkFont(family="Segoe UI", size=14, weight="bold"))
        max_label.grid(row=0, column=0, padx=(5, 0), sticky="nw")

        youtube_link = customtkinter.CTkLabel(credits_frame_2, text="YouTube",
                                             font=("Segoe UI", 12, "underline"),
                                             text_color="dodgerblue", cursor="hand2")
        youtube_link.grid(row=1, column=0, padx=(5, 0), sticky="nw")
        youtube_link.bind("<Button-1>", lambda e: webbrowser.open("https://youtube.com/@maxstellar_"))

        # Row 2: sols_sniper (dannw & yeswe)
        try:
            sols_sniper_path = _asset_path("sols_sniper.png")
            if os.path.exists(sols_sniper_path):
                sols_sniper = customtkinter.CTkImage(dark_image=Image.open(sols_sniper_path), size=(60, 60))
                sols_sniper_label = customtkinter.CTkLabel(parent, image=sols_sniper, text="")
                sols_sniper_label.grid(row=2, column=0, padx=(10, 0), pady=(5, 0), sticky="w")

                sols_sniper_label.image = sols_sniper
        except:
            pass

        credits_frame_3 = customtkinter.CTkFrame(parent)
        credits_frame_3.grid(row=2, column=1, padx=(7, 0), pady=(5, 0), sticky="w")

        sniper_label = customtkinter.CTkLabel(credits_frame_3, text="dannw & yeswe - Developers",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=14, weight="bold"))
        sniper_label.grid(row=0, column=0, padx=(5, 0), sticky="nw")

        support_link = customtkinter.CTkLabel(credits_frame_3, text="Discord",
                                             font=("Segoe UI", 12, "underline"),
                                             text_color="dodgerblue", cursor="hand2")
        support_link.grid(row=1, column=0, padx=(5, 0), sticky="nw")
        support_link.bind("<Button-1>", lambda e: webbrowser.open("https://discord.gg/solsniper"))

    def _build_control_buttons(self):
        self.start_button = customtkinter.CTkButton(self.root, text="Start",
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                                    width=75,
                                                    command=self.start_macro)
        self.start_button.grid(row=1, column=0, padx=(10, 0), pady=(10, 10), sticky="w")

        self.pause_button = customtkinter.CTkButton(self.root, text="Pause",
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                                    width=75,
                                                    command=self.pause_macro)
        self.pause_button.grid(row=1, column=1, padx=(5, 0), pady=(10, 10), sticky="w")

        self.stop_button = customtkinter.CTkButton(self.root, text="Stop",
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                                   width=75,
                                                   command=self.stop_macro)
        self.stop_button.grid(row=1, column=2, padx=(5, 10), pady=(10, 10), sticky="w")

        self.shortcut_label = customtkinter.CTkLabel(
            self.root,
            text="Shortcuts: F1 Start/Resume  |  F2 Stop  |  F3 Pause",
            font=customtkinter.CTkFont(family="Segoe UI", size=13)
        )
        self.shortcut_label.grid(row=2, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="w")

    def open_configure_pings(self):
        window = customtkinter.CTkToplevel(self.root)
        window.title("Configure Pings")
        window.geometry("530x270")
        window.resizable(False, False)

        label = customtkinter.CTkLabel(window, text="Choose what you get notified for!",
                                      font=customtkinter.CTkFont(family="Segoe UI", size=20))
        label.grid(row=0, column=0, columnspan=4, pady=10, padx=10)

        biomes = [
            ("Windy", "windy", 1, 0),
            ("Snowy", "snowy", 2, 0),
            ("Rainy", "rainy", 3, 0),
            ("Sand Storm", "sand_storm", 4, 0),
            ("Hell", "hell", 1, 2),
            ("Starfall", "starfall", 2, 2),
            ("Corruption", "corruption", 3, 2),
            ("Null", "null", 4, 2)
        ]

        for display_name, key, row, col_offset in biomes:
            biome_label = customtkinter.CTkLabel(window, text=display_name,
                                                font=customtkinter.CTkFont(family="Segoe UI", size=18))
            biome_label.grid(row=row, column=col_offset, padx=(10, 0), pady=10, sticky="w")

            dropdown = customtkinter.CTkOptionMenu(window,
                                                  values=["Message", "Ping", "Nothing"],
                                                  font=customtkinter.CTkFont(family="Segoe UI", size=18),
                                                  variable=self.biome_vars[key],
                                                  command=lambda val, k=key: self._save_biome_config(k, val))
            dropdown.grid(row=row, column=col_offset+1, padx=10, pady=10, sticky="w")

    def _save_biome_config(self, biome_key, value):
        self.config.set('Biomes', biome_key, value)
        with open(self.config_name, 'w') as f:
            self.config.write(f)
        print(f"[Config] Saved {biome_key} = {value}")

    def _save_anti_afk_settings(self):
        if not self.config.has_section('Macro'):
            self.config.add_section('Macro')

        self.config.set('Macro', 'anti_afk', str(self.anti_afk_enabled.get()))
        self.config.set('Macro', 'anti_afk_interval', self.anti_afk_interval.get())

        with open(self.config_name, 'w') as f:
            self.config.write(f)
        print(f"[Config] Saved Anti-AFK settings: enabled={self.anti_afk_enabled.get()}, interval={self.anti_afk_interval.get()}")

    def _save_roblox_monitor_settings(self):
        if not self.config.has_section('Macro'):
            self.config.add_section('Macro')

        self.config.set('Macro', 'roblox_monitor', str(self.roblox_monitor_enabled.get()))

        with open(self.config_name, 'w') as f:
            self.config.write(f)
        print(f"[Config] Saved Roblox Monitor settings: enabled={self.roblox_monitor_enabled.get()}")

    def _schedule_hotkey_dispatch(self):
        if not self.destroyed and self._hotkey_dispatch_after_id is None:
            self._hotkey_dispatch_after_id = self.root.after(50, self._dispatch_global_hotkeys)

    def _dispatch_global_hotkeys(self):
        self._hotkey_dispatch_after_id = None
        if self.destroyed:
            return

        while True:
            try:
                command = self._hotkey_commands.get_nowait()
            except queue.Empty:
                break

            if command == "start":
                self._on_hotkey_start()
            elif command == "stop":
                self._on_hotkey_stop()
            elif command == "pause":
                self._on_hotkey_pause()

        self._schedule_hotkey_dispatch()

    def _start_global_hotkeys(self):
        if self._global_hotkeys.start():
            print("[Hotkeys] Global F1/F2/F3 hotkeys registered")
            return

        error = self._global_hotkeys.error or "Unknown registration error"
        print(f"[Hotkeys] Global hotkeys unavailable: {error}")
        self.shortcut_label.configure(text="Global hotkeys unavailable - use the buttons")

    def _stop_global_hotkeys(self):
        if self._hotkey_dispatch_after_id is not None:
            try:
                self.root.after_cancel(self._hotkey_dispatch_after_id)
            except Exception:
                pass
            self._hotkey_dispatch_after_id = None
        self._global_hotkeys.stop()

    def _on_hotkey_start(self, event=None):
        if not self.started or self.paused:
            self.start_macro()
        return "break"

    def _on_hotkey_stop(self, event=None):
        if self.started:
            self.stop_macro()
        return "break"

    def _on_hotkey_pause(self, event=None):
        if self.started and not self.paused:
            self.pause_macro()
        return "break"

    def start_macro(self):
        if self.started and not self.paused:
            return

        if self.paused:
            self.paused = False
            self.root.title("perdstellar's Macro - Running")
            print("[Macro] Resumed")
            return

        webhook_url = self.webhook_field.get().strip()
        if not webhook_url or 'discord' not in webhook_url or 'https://' not in webhook_url:
            ctypes.windll.user32.MessageBoxW(0, "Invalid or missing webhook link.", "Error", 0)
            return

        discord_id = self.discid_field.get().strip()
        if discord_id and not discord_id.isdigit():
            ctypes.windll.user32.MessageBoxW(0, "Discord User ID should only contain numbers.", "Error", 0)
            return

        self.config.set('Webhook', 'webhook_url', webhook_url)
        self.config.set('Webhook', 'private_server', self.ps_field.get().strip())
        self.config.set('Webhook', 'discord_user_id', discord_id)
        with open(self.config_name, 'w') as f:
            self.config.write(f)

        self.webhook_field.configure(state="disabled", text_color="gray")
        self.ps_field.configure(state="disabled", text_color="gray")
        self.discid_field.configure(state="disabled", text_color="gray")

        self.webhook_urls = self._parse_webhook_urls()

        self._send_status_webhook("Macro started!", 0x64ff5e)

        # set started flag before starting threads
        self.started = True

        self.tracker.start_detection()

        if self.anti_afk_enabled.get():
            self._start_anti_afk()

        if self.roblox_monitor_enabled.get():
            self._start_roblox_monitor()

        self.root.title("perdstellar's Macro - Running")
        print("[Macro] Started")

    def pause_macro(self):
        if not self.started:
            return

        if not self.paused:
            self.paused = True
            self.root.title("perdstellar's Macro - Paused")
            print("[Macro] Paused")

    def stop_macro(self):
        if not self.started:
            self.root.quit()
            return

        self.tracker.stop_detection()

        self._stop_anti_afk()

        self._stop_roblox_monitor()

        self._send_status_webhook("Macro stopped.", 0xff4719)

        self.webhook_field.configure(state="normal", text_color="white")
        self.ps_field.configure(state="normal", text_color="white")
        self.discid_field.configure(state="normal", text_color="white")

        self.started = False
        self.paused = False
        self.root.title("perdstellar's Macro - Stopped")
        print("[Macro] Stopped")

    def on_close(self):
        if self.destroyed:
            return

        self.destroyed = True
        self._stop_global_hotkeys()
        if self.started:
            self.stop_macro()
        self.root.quit()
        self.root.destroy()

    def on_biome_change(self, new_biome, old_biome):
        if self.paused or not self.started:
            return

        print(f"[Callback] Biome changed: {old_biome} -> {new_biome}")

        # send "ended" webhook for previous biome
        if old_biome and old_biome != "NORMAL":
            biome_key = old_biome.lower().replace(" ", "_")

            # get notification type for the old biome
            if biome_key in self.biome_vars:
                notif_type = self.biome_vars[biome_key].get()
            else:
                # for biomes not in config (new/rare biomes), default to Ping
                notif_type = "Ping" if old_biome in self.RARE_BIOMES else "Message"

            if notif_type != "Nothing":
                self._send_biome_webhook(old_biome, "end", notif_type)

        # send "started" webhook for new biome
        if new_biome != "NORMAL":
            biome_key = new_biome.lower().replace(" ", "_")

            # default for new biomes - message, ping for rare
            if biome_key not in self.biome_vars:
                notif_type = "Ping" if new_biome in self.RARE_BIOMES else "Message"
            else:
                notif_type = self.biome_vars[biome_key].get()

            if notif_type != "Nothing" or new_biome in self.RARE_BIOMES:
                self._send_biome_webhook(new_biome, "start", notif_type)

    def _send_status_webhook(self, message, color):
        if not self.webhook_urls:
            return

        embed = {
            "description": f"[{time.strftime('%H:%M:%S')}]: {message}",
            "color": color,
            "footer": {
                "text": "perdstellar's Macro | v1.2",
                "icon_url": "https://raw.githubusercontent.com/eperdak/perdstellar-Macro/ffb828546cfd9ea64b1619065b8b28f8d0a2c857/assets/embed_footer_icon.png"
            }
        }

        for url in self.webhook_urls:
            try:
                payload = {"embeds": [embed]}
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                print(f"[Webhook] Failed to send to {url}: {e}")

    def _send_biome_webhook(self, biome, event_type, notif_type):
        if not self.webhook_urls:
            return

        biome_info = self.tracker.biome_data.get(biome, {})
        color_str = biome_info.get("color", "0xffffff").replace("0x", "")
        try:
            biome_color = int(color_str, 16)
        except:
            biome_color = 0xffffff

        private_server = self.ps_field.get().strip()

        if event_type == "start":
            description = f"> ## Biome Started - {biome}"
        else:
            description = f"> ## Biome Ended - {biome}"

        embed = {
            "title": f"[{time.strftime('%H:%M:%S')}]",
            "description": description,
            "color": biome_color,
            "footer": {
                "text": "perdstellar's Macro | v1.2",
                "icon_url": "https://raw.githubusercontent.com/eperdak/perdstellar-Macro/ffb828546cfd9ea64b1619065b8b28f8d0a2c857/assets/embed_footer_icon.png"
            }
        }

        if event_type == "start" and private_server:
            embed["fields"] = [{"name": "Private Server Link", "value": private_server}]

        thumbnail_url = biome_info.get("thumbnail_url", "")
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        content = ""
        if event_type == "start":
            if biome in self.RARE_BIOMES:
                content = "@everyone"
            elif notif_type == "Ping":
                discord_id = self.discid_field.get().strip()
                if discord_id:
                    content = f"<@{discord_id}>"

        for url in self.webhook_urls:
            try:
                payload = {"content": content, "embeds": [embed]}
                requests.post(url, json=payload, timeout=5)
                print(f"[Webhook] Sent {event_type} notification for {biome}")
            except Exception as e:
                print(f"[Webhook] Failed to send to {url}: {e}")

    def _start_anti_afk(self):
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            return

        self.anti_afk_running = True
        self.anti_afk_thread = threading.Thread(target=self._anti_afk_loop, daemon=True, name="AntiAFK")
        self.anti_afk_thread.start()
        print("[Anti-AFK] Started")

    def _stop_anti_afk(self):
        self.anti_afk_running = False
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            self.anti_afk_thread.join(timeout=2)
        print("[Anti-AFK] Stopped")

    def _start_roblox_monitor(self):
        if self.roblox_monitor_thread and self.roblox_monitor_thread.is_alive():
            return

        self.roblox_monitor_running = True
        self.roblox_monitor_thread = threading.Thread(target=self._roblox_monitor_loop, daemon=True, name="RobloxMonitor")
        self.roblox_monitor_thread.start()
        print("[RobloxMonitor] Started")

    def _stop_roblox_monitor(self):
        self.roblox_monitor_running = False
        if self.roblox_monitor_thread and self.roblox_monitor_thread.is_alive():
            self.roblox_monitor_thread.join(timeout=2)
        print("[RobloxMonitor] Stopped")

    def _roblox_monitor_loop(self):
        print("[RobloxMonitor] Loop started")
        print(f"[RobloxMonitor] Initial state - running={self.roblox_monitor_running}, started={self.started}")

        # initial delay to ensure Roblox is fully loaded
        time.sleep(3)

        # wait for Roblox window to appear initially
        print("[RobloxMonitor] Waiting for Roblox window to appear...")
        while self.roblox_monitor_running and self.started:
            roblox_hwnd = self._find_roblox_window()
            if roblox_hwnd:
                self.roblox_window_handle = roblox_hwnd
                print(f"[RobloxMonitor] Roblox window detected! Handle: {roblox_hwnd}")
                break
            print("[RobloxMonitor] Roblox window not found yet, waiting...")
            time.sleep(3)

        if not self.roblox_monitor_running or not self.started:
            print("[RobloxMonitor] Loop stopped before Roblox window was found")
            return

        # now monitor for window disappearance or handle change with faster polling
        print("[RobloxMonitor] Monitoring Roblox window...")
        while self.roblox_monitor_running and self.started:
            try:
                if self.paused:
                    time.sleep(1)
                    continue

                roblox_hwnd = self._find_roblox_window()

                if not roblox_hwnd:
                    print("[RobloxMonitor] Roblox window not found! Stopping macro...")
                    self._send_status_webhook("Roblox has been closed/crashed! Stopping the detection.", 0xff0000)
                    self.root.after(0, self.stop_macro)
                    break
                elif roblox_hwnd != self.roblox_window_handle:
                    print(f"[RobloxMonitor] Roblox window handle changed from {self.roblox_window_handle} to {roblox_hwnd}! Stopping macro...")
                    self._send_status_webhook("Roblox has been closed/crashed! Stopping the detection.", 0xff0000)
                    self.root.after(0, self.stop_macro)
                    break

                time.sleep(1)

            except Exception as e:
                print(f"[RobloxMonitor] Error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

        print("[RobloxMonitor] Loop stopped")

    def _anti_afk_loop(self):
        print(f"[Anti-AFK] Loop started - running={self.anti_afk_running}, started={self.started}")

        while self.anti_afk_running and self.started:
            try:
                try:
                    interval_min = float(self.anti_afk_interval.get())
                    interval_min = max(1.0, min(20.0, interval_min))
                except Exception as e:
                    print(f"[Anti-AFK] Error parsing interval: {e}")
                    interval_min = 5.0

                interval_sec = interval_min * 60.0
                print(f"[Anti-AFK] Waiting {interval_min} minutes ({interval_sec} seconds)")

                # sleep in small chunks for quick stopping
                elapsed = 0
                while elapsed < interval_sec and self.anti_afk_running and self.started:
                    time.sleep(1)
                    elapsed += 1

                print(f"[Anti-AFK] Wait complete - running={self.anti_afk_running}, started={self.started}")

                if not self.anti_afk_running or not self.started:
                    print("[Anti-AFK] Loop stopped (flag check)")
                    break

                enabled = self.anti_afk_enabled.get()
                print(f"[Anti-AFK] Enabled check: {enabled}")
                if not enabled:
                    print("[Anti-AFK] Disabled, skipping action")
                    continue

                print("[Anti-AFK] Executing action...")
                self._perform_anti_afk_action()

            except Exception as e:
                print(f"[Anti-AFK] Error in loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

        print(f"[Anti-AFK] Loop exited - running={self.anti_afk_running}, started={self.started}")

    def _perform_anti_afk_action(self):
        try:
            print("[Anti-AFK] Starting action...")

            if self.paused:
                print("[Anti-AFK] Macro is paused, skipping")
                return

            print("[Anti-AFK] Looking for Roblox window...")
            roblox_hwnd = self._find_roblox_window()
            if not roblox_hwnd:
                print("[Anti-AFK] Roblox window not found!")
                return

            print(f"[Anti-AFK] Found Roblox window: {roblox_hwnd}")

            try:
                hwnd_before = win32gui.GetForegroundWindow()
                print(f"[Anti-AFK] Current foreground window: {hwnd_before}")
            except:
                hwnd_before = None

            try:
                print("[Anti-AFK] Focusing Roblox window...")
                win32gui.SetForegroundWindow(roblox_hwnd)
                time.sleep(0.3)
                print("[Anti-AFK] Roblox focused successfully")
            except Exception as e:
                print(f"[Anti-AFK] Failed to focus Roblox: {e}")
                return

            try:
                print("[Anti-AFK] Pressing space key...")
                pyautogui.press('space')
                print("[Anti-AFK] jumped in game!")
                time.sleep(0.3)
            except Exception as e:
                print(f"[Anti-AFK] Failed to press space: {e}")

            if hwnd_before and hwnd_before != roblox_hwnd:
                try:
                    print("[Anti-AFK] Restoring previous window focus...")
                    time.sleep(0.2)
                    win32gui.SetForegroundWindow(hwnd_before)
                    print("[Anti-AFK] Focus restored")
                except Exception as e:
                    print(f"[Anti-AFK] Failed to restore focus: {e}")

            print("[Anti-AFK] Action completed successfully")

        except Exception as e:
            print(f"[Anti-AFK] Error performing action: {e}")
            import traceback
            traceback.print_exc()

    def _find_roblox_window(self):
        try:
            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title == "Roblox":
                        windows.append(hwnd)
                return True

            windows = []
            win32gui.EnumWindows(callback, windows)

            if windows:
                return windows[0]

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'roblox' in proc.info['name'].lower():
                        def find_window_by_pid(hwnd, pid_list):
                            if win32gui.IsWindowVisible(hwnd):
                                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                                if found_pid == pid_list[0]:
                                    title = win32gui.GetWindowText(hwnd)
                                    if title == "Roblox":
                                        pid_list[1] = hwnd
                            return True

                        pid_and_hwnd = [proc.info['pid'], None]
                        win32gui.EnumWindows(find_window_by_pid, pid_and_hwnd)
                        if pid_and_hwnd[1]:
                            return pid_and_hwnd[1]
                except:
                    continue

            return None
        except Exception as e:
            print(f"[Anti-AFK] Error finding Roblox window: {e}")
            return None

    def run(self):
        print("[App] Starting perdstellar's Macro...")
        self._start_global_hotkeys()
        try:
            self.root.mainloop()
        finally:
            self._stop_global_hotkeys()


if __name__ == "__main__":
    app = None
    try:
        app = BiomeMacroApp()
        app.root.after_idle(_signal_launcher_ready)
        app.run()
    except KeyboardInterrupt:
        if app is not None:
            app.on_close()
        print("\n[App] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        ctypes.windll.user32.MessageBoxW(0, f"Fatal error: {e}\nCheck crash.log for details.", "Error", 0)
        sys.exit(1)
