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
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# Connect to the core brain (10/10 Architecture)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.decision_engine import evaluate_system_state
from core.driver_analyzer import analyze_drivers
from core.learning_engine import get_learned_ignore_list
from core.ml_model import load_model

# =========================
# PROFESSIONAL UI THEME OVERRIDE
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
TEXT_MAIN = "#FFFFFF"        
TEXT_MUTED = "#A1A1AA"       

# Stealth Matplotlib Styling
plt.rcParams['figure.facecolor'] = CARD_COLOR
plt.rcParams['axes.facecolor'] = CARD_COLOR
plt.rcParams['axes.edgecolor'] = CARD_COLOR
plt.rcParams['text.color'] = TEXT_MUTED
plt.rcParams['axes.labelcolor'] = TEXT_MUTED
plt.rcParams['xtick.color'] = TEXT_MUTED
plt.rcParams['ytick.color'] = TEXT_MUTED
plt.rcParams['grid.color'] = '#1A1A1A'

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

        self.cpu_history = [0] * 30
        self.ram_history = [0] * 30

        self._anomaly_model = None
        self._predictor_model = None
        self._driver_cache = None
        self._driver_last_scan = 0
        self._reboot_ignored = False

        self.build_ui()
        threading.Thread(target=self._preload, daemon=True).start()

    def _preload(self):
        try:
            self._anomaly_model = load_model()
            if os.path.exists(PREDICTOR_MODEL):
                self._predictor_model = joblib.load(PREDICTOR_MODEL)
            print("Models loaded.")
        except Exception as e:
            print(f"Model load error: {e}")

        try:
            from retrain import run_retrain
            silent(run_retrain)
        except Exception as e:
            pass

        self.after(0, self.start_refresh_thread)

    # Local UI helper to format the generic health gauge
    def _calculate_health_score(self, data):
        score = 100
        if data['cpu_percent'] > 80: score -= 25
        elif data['cpu_percent'] > 50: score -= 10
        if data['ram_used_percent'] > 85: score -= 25
        elif data['ram_used_percent'] > 60: score -= 10
        if data['disk_used_percent'] > 90: score -= 20
        elif data['disk_used_percent'] > 70: score -= 10
        return max(score, 0)

    # =========================
    # BUILD UI
    # =========================
    def build_ui(self):
        # Title Bar
        title_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0, height=60)
        title_frame.pack(fill="x", pady=(10, 0))
        title_frame.pack_propagate(False)

        ctk.CTkLabel(
            title_frame, text="⚡ AI-Based E-Booting Optimization System",
            font=ctk.CTkFont(family="Inter", size=18, weight="bold"), text_color=ACCENT_BLUE
        ).pack(side="left", padx=25, pady=15)

        status_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        status_frame.pack(side="right", padx=25)
        
        ctk.CTkLabel(status_frame, text="●", font=ctk.CTkFont(size=18), text_color=ACCENT_GREEN).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(status_frame, text="LIVE", font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=TEXT_MUTED).pack(side="left")

        # --- MASTER AUTOPILOT TOGGLE ---
        self.autopilot_var = ctk.BooleanVar(value=True) 
        self.autopilot_switch = ctk.CTkSwitch(
            status_frame, 
            text="Autopilot", 
            variable=self.autopilot_var,
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            text_color=TEXT_MUTED,
            progress_color=ACCENT_BLUE,
            button_color=TEXT_MAIN,
            button_hover_color="#E4E4E7"
        )
        self.autopilot_switch.pack(side="left", padx=(20, 0))

        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=10)

        # =========================
        # LEFT COLUMN
        # =========================
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
        self.boot_sub = ctk.CTkLabel(boot_card, text="Loading...", font=ctk.CTkFont(family="Consolas", size=12), text_color=TEXT_MUTED)
        self.boot_sub.pack(pady=(0, 18))

        stats_frame = ctk.CTkFrame(left, fg_color="transparent")
        stats_frame.pack(fill="x", pady=10)

        self.cpu_stat = self._make_stat(stats_frame, "CPU", "0%", ACCENT_WARN)
        self.cpu_stat.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.ram_stat = self._make_stat(stats_frame, "RAM", "0%", ACCENT_BLUE)
        self.ram_stat.pack(side="left", fill="both", expand=True, padx=(5, 0))

        reboot_card = ctk.CTkFrame(left, fg_color=CARD_COLOR, corner_radius=8)
        reboot_card.pack(fill="both", expand=True)

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

        # =========================
        # RIGHT COLUMN
        # =========================
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        graph_card = ctk.CTkFrame(right, fg_color=CARD_COLOR, corner_radius=8)
        graph_card.pack(fill="both", expand=True, pady=(0, 10))

        ctk.CTkLabel(graph_card, text="📈 Live System Performance",
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 0))

        self.fig = Figure(figsize=(6, 3), dpi=80)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.18)
        self.graph_canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color('#1A1A1A')
        self.ax.spines['bottom'].set_color('#1A1A1A')
        self._draw_graph()

        bottom_row = ctk.CTkFrame(right, fg_color="transparent")
        bottom_row.pack(fill="both", expand=True)

        # Threat/Autopilot Card
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

        bar = ctk.CTkFrame(self, fg_color="transparent", height=35)
        bar.pack(fill="x", side="bottom", pady=(0, 5))
        bar.pack_propagate(False)

        self.last_update = ctk.CTkLabel(bar, text="Last updated: --", font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED)
        self.last_update.pack(side="left", padx=25)
        ctk.CTkLabel(bar, text="Auto-refresh: 15s", font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED).pack(side="right", padx=25)

    def _make_stat(self, parent, label, value, color):
        frame = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=8)
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(pady=(15, 0))
        lbl = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(family="Inter", size=34, weight="bold"), text_color=color)
        lbl.pack(pady=(0, 15))
        frame.value_label = lbl
        return frame

    def _make_log_card(self, parent, title, text_color):
        card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=8)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family="Inter", size=13, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 5))
        tb = ctk.CTkTextbox(card, fg_color=BG_COLOR, text_color=text_color, font=ctk.CTkFont(family="Consolas", size=13), border_width=0, wrap="word")
        tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tb.insert("end", "Loading...")
        tb.configure(state="disabled")
        card.textbox = tb
        return card

    def _draw_graph(self):
        self.ax.clear()
        x = list(range(30))
        
        self.ax.plot(x, self.cpu_history, color=ACCENT_WARN, linewidth=2, label='CPU %')
        self.ax.fill_between(x, self.cpu_history, alpha=0.08, color=ACCENT_WARN)
        self.ax.plot(x, self.ram_history, color=ACCENT_BLUE, linewidth=2, label='RAM %')
        self.ax.fill_between(x, self.ram_history, alpha=0.15, color=ACCENT_BLUE)
        
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, 29)
        
        self.ax.legend(loc='upper right', fontsize=10, facecolor=CARD_COLOR, edgecolor=CARD_COLOR, labelcolor=TEXT_MAIN)
        self.ax.grid(True, alpha=0.2, color='#1A1A1A', linestyle='--')
        
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color('#1A1A1A')
        self.ax.spines['bottom'].set_color('#1A1A1A')
        self.ax.tick_params(axis='both', colors=TEXT_MUTED, labelsize=10)

        self.graph_canvas.draw()

    def _reboot_now(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Reboot")
        
        width = 380
        height = 180
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
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
                time.sleep(15)
        threading.Thread(target=loop, daemon=True).start()

    def _fetch_data(self):
        result = {}
        try:
            # 1. CORE BRAIN: Call the decoupled decision engine
            state = evaluate_system_state(autopilot_enabled=self.autopilot_var.get())
            result['state'] = state
            result['health'] = state['health']
            
            # 2. Add the learning list for the UI label
            result['learned_ignore'] = list(get_learned_ignore_list())

            # 3. Boot Predictor
            if self._predictor_model and os.path.exists(SUMMARY_FILE):
                df = pd.read_csv(SUMMARY_FILE).tail(1)
                if not df.empty:
                    df['avg_cpu'] = pd.to_numeric(df['avg_cpu'], errors='coerce').fillna(0)
                    df['max_cpu'] = pd.to_numeric(df['max_cpu'], errors='coerce').fillna(0)
                    df['avg_mem'] = pd.to_numeric(df['avg_mem'], errors='coerce').fillna(0)
                    df['max_mem'] = pd.to_numeric(df['max_mem'], errors='coerce').fillna(0)
                    if 'active_procs' not in df.columns:
                        df['active_procs'] = 0
                    df['active_procs'] = pd.to_numeric(df['active_procs'], errors='coerce').fillna(0)
                    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour.fillna(12)
                    df['cpu_spike'] = df['max_cpu'] - df['avg_cpu']
                    features = df[['avg_cpu', 'max_cpu', 'avg_mem', 'max_mem', 'active_procs', 'hour', 'cpu_spike']]
                    result['boot_time'] = round(self._predictor_model.predict(features)[0], 1)

            # 4. Drivers
            now = time.time()
            if self._driver_cache is None or (now - self._driver_last_scan) > 300:
                self._driver_cache = silent(analyze_drivers)
                self._driver_last_scan = now
            result['drivers'] = self._driver_cache

            # 5. Top Processes
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
            
            # Health gauge & Core Stats
            score = self._calculate_health_score(health)
            cpu = health['cpu_percent']
            ram = health['ram_used_percent']

            self.health_gauge.update_value(score, f"CPU:{cpu}% RAM:{ram}%")

            cpu_color = ACCENT_GREEN if cpu < 60 else ACCENT_WARN if cpu < 85 else ACCENT_RED
            ram_color = ACCENT_BLUE if ram < 60 else ACCENT_WARN if ram < 85 else ACCENT_RED
            self.cpu_stat.value_label.configure(text=f"{cpu}%", text_color=cpu_color)
            self.ram_stat.value_label.configure(text=f"{ram}%", text_color=ram_color)

            self.cpu_history.append(cpu)
            self.cpu_history.pop(0)
            self.ram_history.append(ram)
            self.ram_history.pop(0)
            self._draw_graph()

            # Learning UI Update
            if 'learned_ignore' in data:
                learned_list = data['learned_ignore']
                if learned_list:
                    display_list = ", ".join(learned_list[:3])
                    if len(learned_list) > 3:
                        display_list += f" (+{len(learned_list)-3} more)"
                    
                    new_text = f"🧠 Learned to ignore: {display_list}"
                    if self.learning_label.cget("text") != new_text:
                        self.learning_label.configure(text=new_text)

            # ==========================================
            # AUTOPILOT UX INTEGRATION
            # ==========================================
            autopilot_result = state.get('autopilot_feedback')
            
            if not self.autopilot_var.get():
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
                        
                    # FIX: Clear "Loading..." when skipping/stable
                    self.threat_text.configure(state="normal")
                    self.threat_text.delete("1.0", "end")
                    self.threat_text.insert("1.0", "✓ No threats detected\nSystem running normally.\n\nAutopilot is standing by.")
                    self.threat_text.configure(state="disabled")

            else:
                self.agent_status_label.configure(text="✓ System Stable", text_color=ACCENT_GREEN)
                # FIX: Clear "Loading..." when fully stable and Autopilot is asleep
                self.threat_text.configure(state="normal")
                self.threat_text.delete("1.0", "end")
                self.threat_text.insert("1.0", "✓ No threats detected\nSystem running normally.\n\nAutopilot is standing by.")
                self.threat_text.configure(state="disabled")

                
            # Reboot intelligence panel
            reboot_score = state['reboot_score']
            reboot_status = state['reboot_status']

            gauge_color = ACCENT_GREEN if reboot_score < 30 else ACCENT_WARN if reboot_score < 60 else ACCENT_RED
            self.reboot_gauge.update_value(reboot_score, reboot_status)

            label_color = ACCENT_GREEN if reboot_score < 30 else ACCENT_WARN if reboot_score < 60 else ACCENT_RED
            self.reboot_status_label.configure(text=f"{'✓' if reboot_score < 30 else '⚠'} {reboot_status}", text_color=label_color)

            if not self._reboot_ignored:
                self.reboot_text.configure(state="normal")
                self.reboot_text.delete("1.0", "end")

                if state['recommendations']:
                    for r in state['recommendations']: 
                        self.reboot_text.insert("end", f"🔴 {r}\n")
                else:
                    self.reboot_text.insert("end", "✓ No issues detected\n")

                if state['score_breakdown']:
                    self.reboot_text.insert("end", "\n─── Why this score? ───\n")
                    for reason, pts in state['score_breakdown']: 
                        self.reboot_text.insert("end", f"  {'+' if pts > 0 else ''}{pts}  {reason}\n")

                self.reboot_text.configure(state="disabled")

            if reboot_score >= 30 and not self._reboot_ignored:
                self.reboot_btn.configure(state="normal")
                self.ignore_btn.configure(state="normal")
            elif not self._reboot_ignored:
                self.reboot_btn.configure(state="disabled")
                self.ignore_btn.configure(state="disabled")

            # Boot time
            if 'boot_time' in data:
                self.boot_label.configure(text=f"{data['boot_time']} sec")
                self.boot_sub.configure(text="Based on last boot summary")

            # Drivers (Final Production-Grade Intelligence Layer)
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

            # Processes
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