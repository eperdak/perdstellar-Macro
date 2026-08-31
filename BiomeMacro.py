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

            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(__file__)

            icon_path = os.path.join(base_path, 'icon.ico')
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
            "EGGLAND": {"color": "0xd4fc8d", "thumbnail_url": "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/images/EGGLAND.png"}
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

    def _get_latest_log_file(self):
        if not os.path.exists(self.logs_dir):
            return None

        try:
            files = [os.path.join(self.logs_dir, f) for f in os.listdir(self.logs_dir)
                     if f.endswith('.log') and 'Installer' not in f]

            if not files:
                return None

            return max(files, key=os.path.getmtime)
        except Exception as e:
            print(f"[BiomeTracker] Error finding log file: {e}")
            return None

    def _read_log_file(self, log_file_path):
        if not os.path.exists(log_file_path):
            return []

        # reset position if file changed
        if self.log_file_path != log_file_path:
            self.log_file_path = log_file_path
            self.last_position = 0

        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                file.seek(self.last_position)
                lines = file.readlines()
                self.last_position = file.tell()
                return lines
        except Exception as e:
            print(f"[BiomeTracker] Error reading log: {e}")
            return []

    def _check_biome_in_logs(self, log_file_path):
        log_lines = self._read_log_file(log_file_path)

        for line in reversed(log_lines):
            if '[BloxstrapRPC]' in line and '"largeImage"' in line:
                match = re.search(r'"largeImage"\s*:\s*\{[^}]*"hoverText"\s*:\s*"([^"]+)"', line)
                if match:
                    biome = match.group(1).strip().upper()

                    # add unknown biomes to data
                    if biome not in self.biome_data and biome != "NORMAL":
                        print(f"[BiomeTracker] New biome detected: {biome}")
                        self.biome_data[biome] = {
                            "color": "0xffffff",
                            "thumbnail_url": "https://raw.githubusercontent.com/xVapure/Noteab-Macro/refs/heads/main/images/biome_placeholder.png"
                        }

                    if biome != self.current_biome:
                        with self.lock:
                            old_biome = self.current_biome
                            self.current_biome = biome

                        print(f"[BiomeTracker] Biome changed: {old_biome} -> {biome}")

                        # trigger callback
                        if self.biome_callback:
                            try:
                                threading.Thread(
                                    target=self.biome_callback,
                                    args=(biome, old_biome),
                                    daemon=True
                                ).start()
                            except Exception as e:
                                print(f"[BiomeTracker] Callback error: {e}")
                    return

    def _detection_loop(self):
        last_log_file = None

        while self.detection_running:
            try:
                current_log_file = self._get_latest_log_file()

                if current_log_file and current_log_file != last_log_file:
                    self.last_position = 0
                    last_log_file = current_log_file
                    print(f"[BiomeTracker] Using log file: {current_log_file}")

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


class BiomeMacroApp:

    RARE_BIOMES = ["GLITCHED", "DREAMSPACE", "CYBERSPACE"]

    def __init__(self):
        customtkinter.set_default_color_theme("dark-blue")
        self.root = customtkinter.CTk()
        self.root.title("perdstellar's Macro")
        self.root.geometry('505x285')
        self.root.resizable(False, False)

        # set icon for window
        if getattr(sys, 'frozen', False):
            # running as compiled exe
            base_path = sys._MEIPASS
        else:
            # running as script
            base_path = os.path.dirname(__file__)

        icon_path = os.path.join(base_path, 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass

        self.started = False
        self.paused = False
        self.destroyed = False

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

        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

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
                'anti_afk_interval': "5"
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
        tabview = customtkinter.CTkTabview(self.root, width=505, height=230)
        tabview.grid(row=0, column=0, sticky='nsew', columnspan=75)
        tabview.add("Webhook")
        tabview.add("Macro")
        tabview.add("Credits")
        tabview._segmented_button.configure(font=customtkinter.CTkFont(family="Segoe UI", size=16))
        tabview._segmented_button.grid(sticky="w", padx=15)

        self._build_webhook_tab(tabview.tab("Webhook"))

        self._build_macro_tab(tabview.tab("Macro"))

        self._build_credits_tab(tabview.tab("Credits"))

        self._build_control_buttons()

        tabview.set("Webhook")

    def _build_webhook_tab(self, parent):
        # Webhook URL
        webhook_label = customtkinter.CTkLabel(parent, text="Webhook URL:",
                                               font=customtkinter.CTkFont(family="Segoe UI", size=20))
        webhook_label.grid(column=0, row=0, columnspan=2, padx=(10, 0), pady=(5, 0), sticky="w")

        self.webhook_field = customtkinter.CTkEntry(parent,
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                    width=335)
        webhook_value = self.config.get('Webhook', 'webhook_url', fallback="")
        if webhook_value:
            self.webhook_field.insert(0, webhook_value)
        self.webhook_field.grid(row=0, column=1, padx=(144, 0), pady=(10, 0), sticky="w")

        # Private Server
        ps_label = customtkinter.CTkLabel(parent, text="Private Server URL:",
                                         font=customtkinter.CTkFont(family="Segoe UI", size=20))
        ps_label.grid(column=0, row=1, padx=(10, 0), pady=(20, 0), columnspan=2, sticky="w")

        self.ps_field = customtkinter.CTkEntry(parent,
                                              font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                              width=300)
        ps_value = self.config.get('Webhook', 'private_server', fallback="")
        if ps_value:
            self.ps_field.insert(0, ps_value)
        self.ps_field.grid(row=1, column=1, padx=(179, 0), pady=(23, 0), sticky="w")

        # Discord User ID
        discid_label = customtkinter.CTkLabel(parent, text="Discord User ID:",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20))
        discid_label.grid(column=0, row=2, padx=(10, 0), pady=(20, 0), columnspan=2, sticky="w")

        self.discid_field = customtkinter.CTkEntry(parent,
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                   width=324)
        discid_value = self.config.get('Webhook', 'discord_user_id', fallback="")
        if discid_value:
            self.discid_field.insert(0, discid_value)
        self.discid_field.grid(row=2, column=1, padx=(155, 0), pady=(23, 0), sticky="w")

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

        info_label = customtkinter.CTkLabel(parent,
                                           text="Anti-AFK will jump in-game to prevent disconnect",
                                           font=customtkinter.CTkFont(family="Segoe UI", size=12))
        info_label.grid(row=3, column=0, padx=(10, 0), pady=(20, 0), sticky="w")

    def _build_credits_tab(self, parent):
        dirname = os.path.dirname(__file__)

        try:
            perd_pfp_path = os.path.join(dirname, "perd.png")
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
            max_pfp_path = os.path.join(dirname, "maxstellar.png")
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
            sols_sniper_path = os.path.join(dirname, "sols_sniper.png")
            if os.path.exists(sols_sniper_path):
                sols_sniper = customtkinter.CTkImage(dark_image=Image.open(sols_sniper_path), size=(60, 60))
                sols_sniper_label = customtkinter.CTkLabel(parent, image=sols_sniper, text="")
                sols_sniper_label.grid(row=2, column=0, padx=(10, 0), pady=(5, 0), sticky="w")
                # сохраняем ссылку чтобы не удалилось сборщиком мусора
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
        self.start_button.grid(row=1, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

        self.pause_button = customtkinter.CTkButton(self.root, text="Pause",
                                                    font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                                    width=75,
                                                    command=self.pause_macro)
        self.pause_button.grid(row=1, column=1, padx=(5, 0), pady=(10, 0), sticky="w")

        self.stop_button = customtkinter.CTkButton(self.root, text="Stop",
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"),
                                                   width=75,
                                                   command=self.stop_macro)
        self.stop_button.grid(row=1, column=2, padx=(5, 0), pady=(10, 0), sticky="w")

    def open_configure_pings(self):
        window = customtkinter.CTkToplevel(self.root)
        window.title("Configure Pings")
        window.geometry("600x400")

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

    def start_macro(self):
        if self.started:
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

        self.root.title("perdstellar's Macro - Running")
        print("[Macro] Started")

    def pause_macro(self):
        if not self.started:
            return

        self.paused = not self.paused
        if self.paused:
            self.root.title("perdstellar's Macro - Paused")
            print("[Macro] Paused")
        else:
            self.root.title("perdstellar's Macro - Running")
            print("[Macro] Resumed")

    def stop_macro(self):
        if not self.started:
            self.root.quit()
            return

        self.tracker.stop_detection()

        self._stop_anti_afk()

        self._send_status_webhook("Macro stopped.", 0xff4719)

        self.webhook_field.configure(state="normal", text_color="white")
        self.ps_field.configure(state="normal", text_color="white")
        self.discid_field.configure(state="normal", text_color="white")

        self.started = False
        self.paused = False
        self.root.title("perdstellar's Macro - Stopped")
        print("[Macro] Stopped")

    def on_close(self):
        self.destroyed = True
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
            if biome_key in self.biome_vars:
                notif_type = self.biome_vars[biome_key].get()
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
                "text": "perdstellar's Macro | v1.0",
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
                "text": "perdstellar's Macro | v1.0",
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
                    if title and "Roblox" in title:
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
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = BiomeMacroApp()
        app.run()
    except KeyboardInterrupt:
        print("\n[App] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        ctypes.windll.user32.MessageBoxW(0, f"Fatal error: {e}\nCheck crash.log for details.", "Error", 0)
        sys.exit(1)
