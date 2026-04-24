import sys
import io
import datetime
import threading
import time
import psutil
import joblib
import os
import pandas as pd
import customtkinter as ctk

# Connect to the core brain
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.decision_engine import evaluate_system_state
from core.driver_analyzer import analyze_drivers
from core.learning_engine import get_learned_ignore_list
from core.ml_model import load_model

# Import the simulator
try:
    from simulate import cpu_stress, ram_stress
except ImportError:
    pass

# =========================
# PROFESSIONAL UI THEME
# =========================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# HUD Color Palette
BG_COLOR = "#050505"         
CARD_COLOR = "#0F0F11"       
ACCENT_BLUE = "#00E5FF"      
ACCENT_GREEN = "#00FF41"     
ACCENT_RED = "#FF003C"       
ACCENT_WARN = "#FFB000"      
ACCENT_PURPLE = "#8A2BE2"    
TEXT_MAIN = "#FFFFFF"        
TEXT_MUTED = "#A1A1AA"       

PREDICTOR_MODEL = "data/boot_predictor.pkl"
SUMMARY_FILE = "data/boot_summary.csv"

def silent(func, *args, **kwargs):
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        result = func(*args, **kwargs)
    finally:
        sys.stdout = old
    return result

# =========================
# GAUGE WIDGET 
# =========================
class GaugeCanvas(ctk.CTkFrame):
    def __init__(self, parent, title, color, **kwargs):
        super().__init__(parent, fg_color=CARD_COLOR, corner_radius=8, border_width=0, **kwargs)
        self.color = color
        self._last_value = -1
        self._arc = None
        self._value_text = None
        self._sub_text = None

        self.canvas = ctk.CTkCanvas(self, bg=CARD_COLOR, highlightthickness=0, width=220, height=140)
        self.canvas.pack(pady=(15, 0))

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(pady=(0, 10))

        self.canvas.after(100, self._draw_background)

    def _draw_background(self):
        self.canvas.create_arc(25, 10, 195, 140, start=0, extent=180,
                               style="arc", outline="#1A1A1A", width=8)
        self._value_text = self.canvas.create_text(
            110, 100, text="--", font=("Inter", 42, "bold"), fill=TEXT_MAIN
        )
        self._sub_text = self.canvas.create_text(
            110, 130, text="", font=("Consolas", 11), fill=TEXT_MUTED
        )
        self._arc = self.canvas.create_arc(
            25, 10, 195, 140, start=180, extent=0,
            style="arc", outline=self.color, width=8
        )

    def update_value(self, value, subtitle=""):
        if value == self._last_value:
            return
        self._last_value = value
        if self._arc is None:
            return
        extent = int((value / 100) * 180)
        self.canvas.itemconfig(self._arc, extent=-extent)
        self.canvas.itemconfig(self._value_text, text=str(int(value)))
        self.canvas.itemconfig(self._sub_text, text=subtitle)

# =========================
# MAIN DASHBOARD
# =========================
class AIBootDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI-Based E-Booting Optimization System")
        self.geometry("1400x850")
        self.resizable(True, True)
        self.configure(fg_color=BG_COLOR)
        self.running = True

        self._anomaly_model = None
        self._predictor_model = None
        self._driver_cache = None
        self._driver_last_scan = 0
        self._reboot_ignored = False
        self._autopilot_enabled = True 

        self.build_ui()
        threading.Thread(target=self._preload, daemon=True).start()

    def _preload(self):
        try:
            self._anomaly_model = load_model()
            if os.path.exists(PREDICTOR_MODEL):
                self._predictor_model = joblib.load(PREDICTOR_MODEL)
        except Exception:
            pass

        try:
            from retrain import run_retrain
            silent(run_retrain)
        except Exception:
            pass

        self.after(0, self.start_refresh_thread)

    def _calculate_health_score(self, data):
        score = 100
        if data['cpu_percent'] > 80: score -= 25
        elif data['cpu_percent'] > 50: score -= 10
        if data['ram_used_percent'] > 85: score -= 25
        elif data['ram_used_percent'] > 60: score -= 10
        if data['disk_used_percent'] > 90: score -= 20
        elif data['disk_used_percent'] > 70: score -= 10
        return max(score, 0)

    def _run_simulation(self):
        self.demo_btn.configure(state="disabled", text="⚠️ Spiking System...", fg_color=ACCENT_WARN, text_color="#000000")
        
        def stress_thread():
            try:
                c_thread = threading.Thread(target=cpu_stress, args=(60,))
                r_thread = threading.Thread(target=ram_stress, args=(60,))
                c_thread.start()
                r_thread.start()
                c_thread.join()
                r_thread.join()
            except Exception:
                pass
            
            self.after(0, lambda: self.demo_btn.configure(
                state="normal", text="🧪 Simulate Spike", fg_color=ACCENT_PURPLE, text_color=TEXT_MAIN
            ))

        threading.Thread(target=stress_thread, daemon=True).start()

    def _toggle_autopilot(self):
        self._autopilot_enabled = self.autopilot_var.get()

    def build_ui(self):
        # HEADER
        title_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0, height=60)
        title_frame.pack(fill="x", pady=(10, 0))
        title_frame.pack_propagate(False)

        ctk.CTkLabel(
            title_frame, text="⚡ AI-Based E-Booting Optimization System",
            font=ctk.CTkFont(family="Inter", size=18, weight="bold"), text_color=ACCENT_BLUE
        ).pack(side="left", padx=25, pady=15)

        status_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        status_frame.pack(side="right", padx=25)
        
        self.demo_btn = ctk.CTkButton(
            status_frame, text="🧪 Simulate Spike", 
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color=ACCENT_PURPLE, text_color=TEXT_MAIN, hover_color="#6A1B9A",
            command=self._run_simulation, height=32, width=140
        )
        self.demo_btn.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(status_frame, text="●", font=ctk.CTkFont(size=18), text_color=ACCENT_GREEN).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(status_frame, text="LIVE", font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=TEXT_MUTED).pack(side="left")

        self.autopilot_var = ctk.BooleanVar(value=True) 
        self.autopilot_switch = ctk.CTkSwitch(
            status_frame, 
            text="Autopilot", 
            variable=self.autopilot_var,
            command=self._toggle_autopilot,
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            text_color=TEXT_MUTED,
            progress_color=ACCENT_BLUE,
            button_color=TEXT_MAIN,
            button_hover_color="#E4E4E7"
        )
        self.autopilot_switch.pack(side="left", padx=(20, 0))

        # MAIN CONTENT AREA
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=10)

        # LEFT COLUMN (Gauges & Reboot Intel)
        left = ctk.CTkFrame(main, fg_color="transparent", width=380)
        left.pack(side="left", fill="y", padx=(0, 15))
        left.pack_propagate(False)

        gauge_frame = ctk.CTkFrame(left, fg_color="transparent")
        gauge_frame.pack(fill="x")

        self.health_gauge = GaugeCanvas(gauge_frame, "Health Score", ACCENT_GREEN)
        self.health_gauge.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.reboot_gauge = GaugeCanvas(gauge_frame, "Reboot Score", ACCENT_WARN)
        self.reboot_gauge.pack(side="left", fill="both", expand=True, padx=(5, 0))

        boot_card = ctk.CTkFrame(left, fg_color=CARD_COLOR, corner_radius=8)
        boot_card.pack(fill="x", pady=(10, 0))

        ctk.CTkLabel(boot_card, text="Predicted Boot Time",
                     font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 0))

        self.boot_label = ctk.CTkLabel(boot_card, text="-- sec", font=ctk.CTkFont(family="Inter", size=36, weight="bold"), text_color=TEXT_MAIN)
        self.boot_label.pack(pady=(8, 0))
        self.boot_sub = ctk.CTkLabel(boot_card, text="Awaiting Boot Data...", font=ctk.CTkFont(family="Consolas", size=12), text_color=TEXT_MUTED)
        self.boot_sub.pack(pady=(0, 18))

        reboot_card = ctk.CTkFrame(left, fg_color=CARD_COLOR, corner_radius=8)
        reboot_card.pack(fill="both", expand=True, pady=(10, 0))

        ctk.CTkLabel(reboot_card, text="🧠 Reboot Intelligence",
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 2))

        self.reboot_status_label = ctk.CTkLabel(reboot_card, text="Checking...", font=ctk.CTkFont(family="Consolas", size=15, weight="bold"), text_color=ACCENT_GREEN)
        self.reboot_status_label.pack(anchor="w", padx=15, pady=(2, 8))

        self.reboot_text = ctk.CTkTextbox(
            reboot_card, fg_color=BG_COLOR, text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Consolas", size=13), border_width=0, wrap="word", height=140
        )
        self.reboot_text.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.reboot_text.insert("end", "Loading...")
        self.reboot_text.configure(state="disabled")

        btn_frame = ctk.CTkFrame(reboot_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 15))

        self.reboot_btn = ctk.CTkButton(
            btn_frame, text="🔄 Reboot Now", font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color=ACCENT_RED, text_color=TEXT_MAIN, hover_color="#CC0030", corner_radius=4,
            command=self._reboot_now, height=36, width=140
        )
        self.reboot_btn.pack(side="left", padx=(0, 10))

        self.ignore_btn = ctk.CTkButton(
            btn_frame, text="✕ Ignore", font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color="#1A1A1A", text_color=TEXT_MUTED, hover_color="#2A2A2A", corner_radius=4,
            command=self._ignore_reboot, height=36, width=110
        )
        self.ignore_btn.pack(side="left")

        self.ignored_label = ctk.CTkLabel(reboot_card, text="", font=ctk.CTkFont(family="Consolas", size=12), text_color=TEXT_MUTED)
        self.ignored_label.pack(pady=(0, 10))

        # RIGHT COLUMN (Stock-Style Telemetry & Monitors)
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        telemetry_card = ctk.CTkFrame(right, fg_color=CARD_COLOR, corner_radius=8)
        telemetry_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(telemetry_card, text="📊 Live Telemetry & Trends", font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 5))

        tel_container = ctk.CTkFrame(telemetry_card, fg_color="transparent")
        tel_container.pack(fill="x", padx=10, pady=(0, 15))

        self.cpu_val, self.cpu_trend, self.cpu_bar = self._make_telemetry_block(tel_container, "CPU Load Trend (Live)", ACCENT_WARN, side="left", pad=(0, 5))
        self.ram_val, self.ram_trend, self.ram_bar = self._make_telemetry_block(tel_container, "RAM Load Trend (Live)", ACCENT_BLUE, side="left", pad=(5, 0))

        # Autopilot & Driver Cards
        bottom_row = ctk.CTkFrame(right, fg_color="transparent")
        bottom_row.pack(fill="both", expand=True)

        threat_card = ctk.CTkFrame(bottom_row, fg_color=CARD_COLOR, corner_radius=8)
        threat_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(threat_card, text="⚡ Autopilot & Threats",
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 2))
        
        self.agent_status_label = ctk.CTkLabel(threat_card, text="Monitoring system...", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=TEXT_MUTED)
        self.agent_status_label.pack(anchor="w", padx=15, pady=(0, 2))

        self.learning_label = ctk.CTkLabel(threat_card, text="", font=ctk.CTkFont(family="Consolas", size=11), text_color=ACCENT_BLUE)
        self.learning_label.pack(anchor="w", padx=15, pady=(0, 5))

        self.threat_text = ctk.CTkTextbox(threat_card, fg_color=BG_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(family="Consolas", size=13), border_width=0, wrap="word")
        self.threat_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.threat_text.insert("end", "Loading...")
        self.threat_text.configure(state="disabled")

        driver_card = self._make_log_card(bottom_row, "🔧 Driver Health", TEXT_MUTED)
        driver_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.driver_text = driver_card.textbox
        self.driver_text.tag_config("red", foreground="#FF003C")
        self.driver_text.tag_config("yellow", foreground="#FFB000")
        self.driver_text.tag_config("green", foreground="#00FF41")

        proc_card = self._make_log_card(bottom_row, "💾 Top Memory Processes", ACCENT_BLUE)
        proc_card.pack(side="left", fill="both", expand=True)
        self.process_text = proc_card.textbox

        # FOOTER
        bar = ctk.CTkFrame(self, fg_color="transparent", height=35)
        bar.pack(fill="x", side="bottom", pady=(0, 5))
        bar.pack_propagate(False)

        self.last_update = ctk.CTkLabel(bar, text="Last updated: --", font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED)
        self.last_update.pack(side="left", padx=25)
        ctk.CTkLabel(bar, text="Auto-refresh: 1s", font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED).pack(side="right", padx=25)

    def _make_telemetry_block(self, parent, title, default_color, side, pad):
        block = ctk.CTkFrame(parent, fg_color=BG_COLOR, corner_radius=6)
        block.pack(side=side, fill="both", expand=True, padx=pad)
        
        top_row = ctk.CTkFrame(block, fg_color="transparent")
        top_row.pack(fill="x", padx=15, pady=(12, 5))
        
        ctk.CTkLabel(top_row, text=title, font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=TEXT_MUTED).pack(side="left")
        trend_lbl = ctk.CTkLabel(top_row, text="→ Stable", font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED)
        trend_lbl.pack(side="right")
        
        val_lbl = ctk.CTkLabel(block, text="0.0%", font=ctk.CTkFont(family="Inter", size=34, weight="bold"), text_color=default_color)
        val_lbl.pack(anchor="w", padx=15)
        
        bar = ctk.CTkProgressBar(block, height=8, progress_color=default_color, fg_color="#1A1A1A")
        bar.pack(fill="x", padx=15, pady=(10, 15))
        bar.set(0)
        
        return val_lbl, trend_lbl, bar

    def _make_log_card(self, parent, title, text_color):
        card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=8)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 5))
        tb = ctk.CTkTextbox(card, fg_color=BG_COLOR, text_color=text_color, font=ctk.CTkFont(family="Consolas", size=13), border_width=0, wrap="word")
        tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tb.insert("end", "Loading...")
        tb.configure(state="disabled")
        card.textbox = tb
        return card

    def _reboot_now(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Reboot")
        
        width = 380
        height = 180
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.configure(fg_color=BG_COLOR)
        dialog.grab_set()
        dialog.resizable(False, False)

        ctk.CTkLabel(dialog, text="Are you sure you want to reboot now?", font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=ACCENT_RED).pack(pady=(25, 5))
        ctk.CTkLabel(dialog, text="Save all work before proceeding.", font=ctk.CTkFont(family="Consolas", size=12), text_color=TEXT_MUTED).pack(pady=(0, 25))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(btn_row, text="Yes, Reboot", fg_color=ACCENT_RED, text_color=TEXT_MAIN, hover_color="#CC0030", font=ctk.CTkFont(family="Inter", size=13, weight="bold"), command=lambda: os.system("shutdown /r /t 10"), width=130, height=36, corner_radius=4).pack(side="left", padx=12)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#1A1A1A", text_color=TEXT_MUTED, hover_color="#2A2A2A", font=ctk.CTkFont(family="Inter", size=13, weight="bold"), command=dialog.destroy, width=130, height=36, corner_radius=4).pack(side="left", padx=12)

    def _ignore_reboot(self):
        self._reboot_ignored = True
        self.ignored_label.configure(text="⚠ Ignored for this session")
        self.reboot_btn.configure(state="disabled")
        self.ignore_btn.configure(state="disabled")

    def start_refresh_thread(self):
        def loop():
            while self.running:
                data = self._fetch_data()
                self.after(0, lambda d=data: self._update_ui(d))
                time.sleep(1) # Fast 1-second refresh for real-time tracking
        threading.Thread(target=loop, daemon=True).start()

    def _fetch_data(self):
        result = {}
        try:
            state = evaluate_system_state(autopilot_enabled=self._autopilot_enabled)
            result['state'] = state
            result['health'] = state['health']
            
            result['learned_ignore'] = list(get_learned_ignore_list())

            if self._predictor_model and os.path.exists(SUMMARY_FILE):
                df = pd.read_csv(SUMMARY_FILE).tail(1)
                if not df.empty:
                    for col in ['avg_cpu', 'max_cpu', 'avg_mem', 'max_mem', 'active_procs']:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                        else:
                            df[col] = 0
                    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour.fillna(12)
                    df['cpu_spike'] = df['max_cpu'] - df['avg_cpu']
                    features = df[['avg_cpu', 'max_cpu', 'avg_mem', 'max_mem', 'active_procs', 'hour', 'cpu_spike']]
                    result['boot_time'] = round(self._predictor_model.predict(features)[0], 1)

            now = time.time()
            if self._driver_cache is None or (now - self._driver_last_scan) > 300:
                self._driver_cache = silent(analyze_drivers)
                self._driver_last_scan = now
            result['drivers'] = self._driver_cache

            procs = []
            for proc in psutil.process_iter(['name', 'memory_percent', 'cpu_percent']):
                try: procs.append(proc.info)
                except: pass
            result['procs'] = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:8]

        except Exception as e:
            print(f"Fetch Error: {e}")
            
        return result

    def _update_ui(self, data):
        try:
            if 'state' not in data:
                return
                
            state = data['state']
            health = data['health']
            
            score = self._calculate_health_score(health)
            cpu = health['cpu_percent']
            ram = health['ram_used_percent']

            self.health_gauge.update_value(score, f"CPU:{cpu:.1f}% RAM:{ram:.1f}%")

            # 🔥 1. First-Frame Bias Fix
            if not getattr(self, "initialized", False):
                self.last_cpu = cpu
                self.last_ram = ram
                self.prev_cpu_delta = 0
                self.prev_ram_delta = 0
                self.initialized = True

            # 🔥 2. Balanced Smoothing (0.5 / 0.5)
            cpu_delta = cpu - self.last_cpu
            cpu_delta_smooth = 0.5 * cpu_delta + 0.5 * self.prev_cpu_delta
            self.prev_cpu_delta = cpu_delta_smooth

            ram_delta = ram - self.last_ram
            ram_delta_smooth = 0.5 * ram_delta + 0.5 * self.prev_ram_delta
            self.prev_ram_delta = ram_delta_smooth

            # 🔥 3. Adaptive Dead-Zones
            cpu_dead_zone = max(1.5, 0.02 * cpu)
            ram_dead_zone = max(1.5, 0.02 * ram)

            # 🎯 Ultimate CPU Trend Logic
            cpu_color = ACCENT_GREEN if cpu < 60 else ACCENT_WARN if cpu < 85 else ACCENT_RED
            
            if abs(cpu_delta_smooth) < cpu_dead_zone:
                cpu_trend_txt = "→ Stable"
                cpu_trend_col = TEXT_MUTED
            elif cpu_delta_smooth > 15 and (cpu > 80 or cpu_delta > 25):
                cpu_trend_txt = "↑↑ Spike Detected"
                cpu_trend_col = ACCENT_RED
            elif cpu_delta_smooth > 3:
                cpu_trend_txt = f"↑ +{cpu_delta_smooth:.1f}%"
                cpu_trend_col = ACCENT_WARN
            elif cpu_delta_smooth < -15:
                cpu_trend_txt = "↓↓ Rapid Drop"
                cpu_trend_col = ACCENT_GREEN
            elif cpu_delta_smooth < -3:
                cpu_trend_txt = f"↓ {abs(cpu_delta_smooth):.1f}%"
                cpu_trend_col = ACCENT_GREEN
            else:
                cpu_trend_txt = getattr(self, "cpu_trend_txt", "→ Stable")
                cpu_trend_col = getattr(self, "cpu_trend_col", TEXT_MUTED)

            # 🎯 Ultimate RAM Trend Logic
            ram_color = ACCENT_BLUE if ram < 60 else ACCENT_WARN if ram < 85 else ACCENT_RED
            
            if abs(ram_delta_smooth) < ram_dead_zone:
                ram_trend_txt = "→ Stable"
                ram_trend_col = TEXT_MUTED
            elif ram_delta_smooth > 10 and (ram > 80 or ram_delta > 20):
                ram_trend_txt = "↑↑ Rapid Growth" 
                ram_trend_col = ACCENT_RED
            elif ram_delta_smooth > 3:
                ram_trend_txt = f"↑ +{ram_delta_smooth:.1f}%"
                ram_trend_col = ACCENT_WARN
            elif ram_delta_smooth < -10:
                ram_trend_txt = "↓↓ Rapid Release"
                ram_trend_col = ACCENT_GREEN
            elif ram_delta_smooth < -3:
                ram_trend_txt = f"↓ {abs(ram_delta_smooth):.1f}%"
                ram_trend_col = ACCENT_GREEN
            else:
                ram_trend_txt = getattr(self, "ram_trend_txt", "→ Stable")
                ram_trend_col = getattr(self, "ram_trend_col", TEXT_MUTED)
                
            # Update values
            self.last_cpu = cpu
            self.last_ram = ram
            self.cpu_trend_txt = cpu_trend_txt
            self.cpu_trend_col = cpu_trend_col
            self.ram_trend_txt = ram_trend_txt
            self.ram_trend_col = ram_trend_col

            # Apply Updates to UI
            self.cpu_val.configure(text=f"{cpu:.1f}%", text_color=cpu_color)
            self.cpu_trend.configure(text=cpu_trend_txt, text_color=cpu_trend_col)
            self.cpu_bar.set(cpu / 100)
            self.cpu_bar.configure(progress_color=cpu_color)

            self.ram_val.configure(text=f"{ram:.1f}%", text_color=ram_color)
            self.ram_trend.configure(text=ram_trend_txt, text_color=ram_trend_col)
            self.ram_bar.set(ram / 100)
            self.ram_bar.configure(progress_color=ram_color)

            if 'learned_ignore' in data:
                learned_list = data['learned_ignore']
                if learned_list:
                    display_list = ", ".join(learned_list[:3])
                    if len(learned_list) > 3:
                        display_list += f" (+{len(learned_list)-3} more)"
                    
                    new_text = f"🧠 Learned to ignore: {display_list}"
                    if self.learning_label.cget("text") != new_text:
                        self.learning_label.configure(text=new_text)

            autopilot_result = state.get('autopilot_feedback')
            
            if not self._autopilot_enabled:
                self.agent_status_label.configure(text="⏸ Autopilot Disabled by User", text_color=TEXT_MUTED)
            elif autopilot_result:
                if autopilot_result.get('status') == "executed":
                    ap_data = autopilot_result['data'] if 'data' in autopilot_result else autopilot_result
                    impact = ap_data['impact']
                    actions = ap_data['actions']
                    
                    primary_target = actions[0]['process'] if actions else "Process"
                    status_color = ACCENT_GREEN if ap_data.get('success', True) else ACCENT_WARN
                    
                    self.agent_status_label.configure(
                        text=f"⚡ Action Taken: {primary_target} terminated", text_color=status_color
                    )
                    
                    self.threat_text.configure(state="normal")
                    self.threat_text.delete("1.0", "end")
                    action_type = autopilot_result.get('type', 'system').upper()
                    self.threat_text.insert("1.0", f"\n[AUTOPILOT: {action_type}]\n")
                    
                    metric = "CPU" if "cpu" in action_type.lower() else "RAM"
                    before_val = impact['before'].get(metric.lower(), 100)
                    after_val = impact['after'].get(metric.lower(), 100)
                    self.threat_text.insert("end", f"📉 {metric} reduced: {before_val}% → {after_val}%\n")
                    
                    for action in actions:
                        icon = "✓" if action.get('success', True) else "⚠"
                        freed = action.get('freed', 0)
                        self.threat_text.insert("end", f"  {icon} {action['process']} (Freed {freed}%)\n")
                            
                    self.threat_text.insert("end", "-"*35 + "\n")
                    self.threat_text.configure(state="disabled")

                elif autopilot_result.get('status') == "skipped":
                    reason = autopilot_result.get('message', '').lower()
                    if "cooldown" in reason:
                        self.agent_status_label.configure(text="⏱ Cooldown active (60s)", text_color=TEXT_MUTED)
                    elif "transient" in reason:
                        self.agent_status_label.configure(text="👀 Monitoring transient spike...", text_color=ACCENT_WARN)
                    elif "stable" in reason or "no targets" in reason:
                        self.agent_status_label.configure(text="✓ System Stable", text_color=ACCENT_GREEN)
                        
                    self.threat_text.configure(state="normal")
                    self.threat_text.delete("1.0", "end")
                    self.threat_text.insert("1.0", "✓ No threats detected\nSystem running normally.\n\nAutopilot is standing by.")
                    self.threat_text.configure(state="disabled")

            else:
                self.agent_status_label.configure(text="✓ System Stable", text_color=ACCENT_GREEN)
                self.threat_text.configure(state="normal")
                self.threat_text.delete("1.0", "end")
                self.threat_text.insert("1.0", "✓ No threats detected\nSystem running normally.\n\nAutopilot is standing by.")
                self.threat_text.configure(state="disabled")

            reboot_score = state['reboot_score']
            severity = state.get('severity', 'NORMAL')
            
            gauge_color = ACCENT_GREEN if severity == "NORMAL" else ACCENT_WARN if severity == "WARNING" else ACCENT_RED
            self.reboot_gauge.update_value(reboot_score, severity)

            label_color = ACCENT_GREEN if severity == "NORMAL" else ACCENT_WARN if severity == "WARNING" else ACCENT_RED
            status_icon = "✓" if severity == "NORMAL" else "⚠" if severity == "WARNING" else "🔴"
            self.reboot_status_label.configure(text=f"{status_icon} {severity} ({reboot_score} pts)", text_color=label_color)

            if not self._reboot_ignored:
                self.reboot_text.configure(state="normal")
                self.reboot_text.delete("1.0", "end")

                if state['recommendations']:
                    for r in state['recommendations']: 
                        self.reboot_text.insert("end", f"🔴 {r}\n")
                else:
                    self.reboot_text.insert("end", "✓ No issues detected\n")

                if state.get('breakdown'):
                    self.reboot_text.insert("end", "\n─── Why this score? ───\n")
                    for reason, pts in state['breakdown']: 
                        self.reboot_text.insert("end", f"  {'+' if pts > 0 else ''}{pts}  {reason}\n")

                self.reboot_text.configure(state="disabled")

            if reboot_score >= 30 and not self._reboot_ignored:
                self.reboot_btn.configure(state="normal")
                self.ignore_btn.configure(state="normal")
            elif not self._reboot_ignored:
                self.reboot_btn.configure(state="disabled")
                self.ignore_btn.configure(state="disabled")

            if 'boot_time' in data:
                self.boot_label.configure(text=f"{data['boot_time']} sec")
                self.boot_sub.configure(text="Based on last boot summary")

            if 'driver_data' in state:
                drivers = state['driver_data']['drivers']
                summary = state['driver_data']['summary']
                ratio = summary.get('severity_ratio', 0)
                
                self.driver_text.configure(state="normal")
                self.driver_text.delete("1.0", "end")
                
                if summary['total'] == 0:
                    self.driver_text.insert("end", "⚠️ No driver signatures detected.\nCheck system permissions.")
                else:
                    self.driver_text.insert("end", f"TOTAL SCANNED: {summary['total']}\n")
                    self.driver_text.insert("end", f"FLAGGED: {summary['flagged']} | RATIO: {ratio:.2f}\n")
                    
                    if ratio > 0.15:
                        self.driver_text.insert("end", "STATUS: 🔴 SYSTEM DEGRADATION\n", "red")
                        self.driver_text.insert("end", "INSIGHT: Critical registry rot. High orphaned driver count likely impacting boot latency.\n\n")
                    elif ratio > 0.05:
                        self.driver_text.insert("end", "STATUS: 🟡 MINOR INSTABILITY\n", "yellow")
                        self.driver_text.insert("end", "INSIGHT: Moderate orphaned drivers found. Monitoring for potential system conflicts.\n\n")
                    elif summary['flagged'] > 0:
                        self.driver_text.insert("end", "STATUS: 🟢 HEALTHY (MINOR NOISE)\n", "green")
                        self.driver_text.insert("end", "INSIGHT: Negligible registry noise. Overall system integrity remains high.\n\n")
                    
                    self.driver_text.insert("end", f"PRIMARY THREAT: {summary['top_issue']} (Dominant Type)\n")
                    self.driver_text.insert("end", "—" * 32 + "\n")
                    
                    for d in drivers[:8]:
                        if d['flag'] == "MISSING PATH": icon = "❌"
                        elif d['flag'] == "DISABLED": icon = "⚠️"
                        else: icon = "ℹ️"
                        
                        if d['severity'] >= 4: sev_label = "HIGH"
                        elif d['severity'] >= 1: sev_label = "MEDIUM"
                        else: sev_label = "LOW"
                        
                        self.driver_text.insert("end", f"{icon} {d['display_name'][:25]}\n")
                        self.driver_text.insert("end", f"   TYPE: {d['start_type']} | IMPACT: {sev_label}\n\n")
                        
                    if summary['flagged'] == 0:
                        self.driver_text.insert("end", "✓ SYSTEM INTEGRITY NOMINAL\n", "green")
                        self.driver_text.insert("end", "All registry drivers mapped to valid image paths.")
                    
                self.driver_text.configure(state="disabled")

            if 'procs' in data:
                self.process_text.configure(state="normal")
                self.process_text.delete("1.0", "end")
                for p in data['procs']:
                    self.process_text.insert("end", f"► {p['name'][:25]}\n  RAM: {round(p['memory_percent'], 2)}% | CPU: {p['cpu_percent']}%\n\n")
                self.process_text.configure(state="disabled")

            self.last_update.configure(text=f"Last updated: {datetime.datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            print(f"UI error: {e}")

    def on_closing(self):
        self.running = False
        self.destroy()

if __name__ == "__main__":
    app = AIBootDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()