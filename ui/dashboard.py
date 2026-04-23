import sys
import io
import datetime
import threading
import time
import math
import psutil
import joblib
import os
import subprocess
import pandas as pd
import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.health_monitor import get_system_health, calculate_health_score
from core.driver_analyzer import analyze_drivers
from core.ml_model import load_threat_data, detect_threats, load_model
from core.anomaly_engine import detect_anomalies

# =========================
# PROFESSIONAL UI THEME OVERRIDE
# =========================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# HUD Color Palette
BG_COLOR = "#050505"         # Pure deep black
CARD_COLOR = "#0F0F11"       # Slightly elevated black for panels
ACCENT_BLUE = "#00E5FF"      # Cyber/Neon Blue
ACCENT_GREEN = "#00FF41"     # Matrix Green
ACCENT_RED = "#FF003C"       # Alert Red
ACCENT_WARN = "#FFB000"      # Warning Orange
TEXT_MAIN = "#FFFFFF"        # Crisp White
TEXT_MUTED = "#A1A1AA"       # Brighter Zinc Grey for high visibility

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
# GAUGE WIDGET (Sleeker, Thinner Arcs)
# =========================
class GaugeCanvas(ctk.CTkFrame):
    def __init__(self, parent, title, color, **kwargs):
        super().__init__(parent, fg_color=CARD_COLOR, corner_radius=8,
                         border_width=0, **kwargs)
        self.color = color
        self._last_value = -1
        self._arc = None
        self._value_text = None
        self._sub_text = None

        self.canvas = ctk.CTkCanvas(self, bg=CARD_COLOR,
                                     highlightthickness=0, width=220, height=140)
        self.canvas.pack(pady=(15, 0))

        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(pady=(0, 10))

        self.canvas.after(100, self._draw_background)

    def _draw_background(self):
        # Thinner, sleeker arcs
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
            print(f"Retrain check error: {e}")

        self.after(0, self.start_refresh_thread)

    # =========================
    # BUILD UI
    # =========================
    def build_ui(self):
        # Stealth Title Bar
        title_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0, height=60)
        title_frame.pack(fill="x", pady=(10, 0))
        title_frame.pack_propagate(False)

        # Reverted back to simple title with adjusted size
        ctk.CTkLabel(
            title_frame,
            text="⚡ AI-Based E-Booting Optimization System",
            font=ctk.CTkFont(family="Inter", size=18, weight="bold"),
            text_color=ACCENT_BLUE
        ).pack(side="left", padx=25, pady=15)

        status_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        status_frame.pack(side="right", padx=25)
        
        # Simple live indicator
        ctk.CTkLabel(status_frame, text="●", font=ctk.CTkFont(size=18), text_color=ACCENT_GREEN).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(status_frame, text="LIVE", font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=TEXT_MUTED).pack(side="left")

        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=10)

        # =========================
        # LEFT COLUMN
        # =========================
        left = ctk.CTkFrame(main, fg_color="transparent", width=380)
        left.pack(side="left", fill="y", padx=(0, 15))
        left.pack_propagate(False)

        # Gauges
        gauge_frame = ctk.CTkFrame(left, fg_color="transparent")
        gauge_frame.pack(fill="x")

        self.health_gauge = GaugeCanvas(gauge_frame, "Health Score", ACCENT_GREEN)
        self.health_gauge.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.reboot_gauge = GaugeCanvas(gauge_frame, "Reboot Score", ACCENT_WARN)
        self.reboot_gauge.pack(side="left", fill="both", expand=True, padx=(5, 0))

        # Boot time card (Minimalist)
        boot_card = ctk.CTkFrame(left, fg_color=CARD_COLOR, corner_radius=8)
        boot_card.pack(fill="x", pady=(10, 0))

        # Adjusted text and size for latency
        ctk.CTkLabel(boot_card, text="Predicted Boot Time",
                     font=ctk.CTkFont(family="Inter", size=11, weight="bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 0))

        # Reduced font size for sec output
        self.boot_label = ctk.CTkLabel(boot_card, text="-- sec",
                                        font=ctk.CTkFont(family="Inter", size=36, weight="bold"),
                                        text_color=TEXT_MAIN)
        self.boot_label.pack(pady=(8, 0))
        self.boot_sub = ctk.CTkLabel(boot_card, text="Loading...",
                                      font=ctk.CTkFont(family="Consolas", size=12), text_color=TEXT_MUTED)
        self.boot_sub.pack(pady=(0, 18))

        # CPU / RAM stats
        stats_frame = ctk.CTkFrame(left, fg_color="transparent")
        stats_frame.pack(fill="x", pady=10)

        self.cpu_stat = self._make_stat(stats_frame, "CPU", "0%", ACCENT_WARN)
        self.cpu_stat.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.ram_stat = self._make_stat(stats_frame, "RAM", "0%", ACCENT_BLUE)
        self.ram_stat.pack(side="left", fill="both", expand=True, padx=(5, 0))

        # =========================
        # REBOOT INTELLIGENCE PANEL
        # =========================
        reboot_card = ctk.CTkFrame(left, fg_color=CARD_COLOR, corner_radius=8)
        reboot_card.pack(fill="both", expand=True)

        ctk.CTkLabel(reboot_card, text="🧠 Reboot Intelligence",
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 2))

        self.reboot_status_label = ctk.CTkLabel(
            reboot_card, text="Checking...",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=ACCENT_GREEN
        )
        self.reboot_status_label.pack(anchor="w", padx=15, pady=(2, 8))

        # Terminal-style text box
        self.reboot_text = ctk.CTkTextbox(
            reboot_card, fg_color=BG_COLOR, # Darker inset
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Consolas", size=13),
            border_width=0, wrap="word", height=140
        )
        self.reboot_text.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.reboot_text.insert("end", "Loading...")
        self.reboot_text.configure(state="disabled")

        # Action buttons (Flat & Modern)
        btn_frame = ctk.CTkFrame(reboot_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 15))

        self.reboot_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Reboot Now",
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color=ACCENT_RED,
            text_color=TEXT_MAIN,
            hover_color="#CC0030",
            corner_radius=4,
            command=self._reboot_now,
            height=36,
            width=140
        )
        self.reboot_btn.pack(side="left", padx=(0, 10))

        self.ignore_btn = ctk.CTkButton(
            btn_frame,
            text="✕ Ignore",
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color="#1A1A1A",
            text_color=TEXT_MUTED,
            hover_color="#2A2A2A",
            corner_radius=4,
            command=self._ignore_reboot,
            height=36,
            width=110
        )
        self.ignore_btn.pack(side="left")

        self.ignored_label = ctk.CTkLabel(
            reboot_card, text="",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=TEXT_MUTED
        )
        self.ignored_label.pack(pady=(0, 10))

        # =========================
        # RIGHT COLUMN
        # =========================
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Graph (Seamless Integration)
        graph_card = ctk.CTkFrame(right, fg_color=CARD_COLOR, corner_radius=8)
        graph_card.pack(fill="both", expand=True, pady=(0, 10))

        ctk.CTkLabel(graph_card, text="📈 Live System Performance",
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 0))

        self.fig = Figure(figsize=(6, 3), dpi=80)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.18)
        self.graph_canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        
        # Remove top and right borders on graph for sleekness
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color('#1A1A1A')
        self.ax.spines['bottom'].set_color('#1A1A1A')
        self._draw_graph()

        # Bottom row
        bottom_row = ctk.CTkFrame(right, fg_color="transparent")
        bottom_row.pack(fill="both", expand=True)

        # Threat panel
        threat_card = self._make_log_card(bottom_row, "🔍 Threat Detection", ACCENT_WARN)
        threat_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.threat_text = threat_card.textbox

        # Driver panel
        driver_card = self._make_log_card(bottom_row, "🔧 Driver Health", TEXT_MUTED)
        driver_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.driver_text = driver_card.textbox

        # Process panel
        proc_card = self._make_log_card(bottom_row, "💾 Top Memory Processes", ACCENT_BLUE)
        proc_card.pack(side="left", fill="both", expand=True)
        self.process_text = proc_card.textbox

        # Bottom bar
        bar = ctk.CTkFrame(self, fg_color="transparent", height=35)
        bar.pack(fill="x", side="bottom", pady=(0, 5))
        bar.pack_propagate(False)

        self.last_update = ctk.CTkLabel(bar, text="Last updated: --",
                                         font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED)
        self.last_update.pack(side="left", padx=25)
        ctk.CTkLabel(bar, text="Auto-refresh: 15s",
                     font=ctk.CTkFont(family="Consolas", size=13), text_color=TEXT_MUTED).pack(side="right", padx=25)

    # =========================
    # HELPERS
    # =========================
    def _make_stat(self, parent, label, value, color):
        frame = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=8)
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(pady=(15, 0))
        lbl = ctk.CTkLabel(frame, text=value,
                           font=ctk.CTkFont(family="Inter", size=34, weight="bold"), text_color=color)
        lbl.pack(pady=(0, 15))
        frame.value_label = lbl
        return frame

    def _make_log_card(self, parent, title, text_color):
        card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=8)
        ctk.CTkLabel(card, text=title,
                     font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(15, 5))
        
        tb = ctk.CTkTextbox(card, fg_color=BG_COLOR, text_color=text_color,
                            font=ctk.CTkFont(family="Consolas", size=13),
                            border_width=0, wrap="word")
        tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tb.insert("end", "Loading...")
        tb.configure(state="disabled")
        card.textbox = tb
        return card

    def _draw_graph(self):
        self.ax.clear()
        x = list(range(30))
        
        # Neon glowing effect styling
        self.ax.plot(x, self.cpu_history, color=ACCENT_WARN, linewidth=2, label='CPU %')
        self.ax.fill_between(x, self.cpu_history, alpha=0.08, color=ACCENT_WARN)
        
        self.ax.plot(x, self.ram_history, color=ACCENT_BLUE, linewidth=2, label='RAM %')
        self.ax.fill_between(x, self.ram_history, alpha=0.15, color=ACCENT_BLUE)
        
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, 29)
        
        # Sleek legend with increased font
        self.ax.legend(loc='upper right', fontsize=10,
                       facecolor=CARD_COLOR, edgecolor=CARD_COLOR, labelcolor=TEXT_MAIN)
        self.ax.grid(True, alpha=0.2, color='#1A1A1A', linestyle='--')
        
        # Ensure spines stay hidden after clear
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color('#1A1A1A')
        self.ax.spines['bottom'].set_color('#1A1A1A')
        self.ax.tick_params(axis='both', colors=TEXT_MUTED, labelsize=10)

        self.graph_canvas.draw()

    # =========================
    # REBOOT ACTIONS
    # =========================
    def _reboot_now(self):
        """Show confirmation before rebooting, centered on screen."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Reboot")
        
        # Calculate screen center logic
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

        ctk.CTkLabel(
            dialog,
            text="Are you sure you want to reboot now?",
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=ACCENT_RED
        ).pack(pady=(25, 5))

        ctk.CTkLabel(
            dialog,
            text="Save all work before proceeding.",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=TEXT_MUTED
        ).pack(pady=(0, 25))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="Yes, Reboot", fg_color=ACCENT_RED, text_color=TEXT_MAIN,
            hover_color="#CC0030", font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            command=lambda: os.system("shutdown /r /t 10"), width=130, height=36, corner_radius=4
        ).pack(side="left", padx=12)

        ctk.CTkButton(
            btn_row, text="Cancel", fg_color="#1A1A1A", text_color=TEXT_MUTED,
            hover_color="#2A2A2A", font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            command=dialog.destroy, width=130, height=36, corner_radius=4
        ).pack(side="left", padx=12)

    def _ignore_reboot(self):
        """Ignore reboot suggestion for this session."""
        self._reboot_ignored = True
        self.ignored_label.configure(text="⚠ Ignored for this session")
        self.reboot_btn.configure(state="disabled")
        self.ignore_btn.configure(state="disabled")

    # =========================
    # DATA FETCH
    # =========================
    def start_refresh_thread(self):
        def loop():
            while self.running:
                data = self._fetch_data()
                self.after(0, lambda d=data: self._update_ui(d))
                time.sleep(15)
        threading.Thread(target=loop, daemon=True).start()

    def _fetch_data(self):
        result = {}

        # Health
        try:
            health = get_system_health()
            result['health'] = health
            result['health_score'] = calculate_health_score(health)
        except Exception as e:
            print(f"Health error: {e}")

        # Anomaly engine
        try:
            result['anomalies'] = detect_anomalies()
        except Exception as e:
            print(f"Anomaly error: {e}")

        # Boot prediction
        try:
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
                    features = df[['avg_cpu', 'max_cpu', 'avg_mem', 'max_mem',
                                   'active_procs', 'hour', 'cpu_spike']]
                    result['boot_time'] = round(self._predictor_model.predict(features)[0], 1)
        except Exception as e:
            print(f"Predictor error: {e}")

        # Threat detection
        try:
            if self._anomaly_model:
                df = load_threat_data()
                if df is not None:
                    df = df.tail(500)
                    res_df = silent(detect_threats, df, self._anomaly_model)
                    if res_df is not None:
                        suspicious = res_df[res_df['threat_level'] == 'SUSPICIOUS']
                        suspicious = suspicious.drop_duplicates(subset='name').head(10)
                        result['suspicious'] = suspicious
        except Exception as e:
            print(f"Threat error: {e}")

        # Drivers — cached 5 minutes
        try:
            now = time.time()
            if self._driver_cache is None or (now - self._driver_last_scan) > 300:
                self._driver_cache = silent(analyze_drivers)
                self._driver_last_scan = now
            result['drivers'] = self._driver_cache
        except Exception as e:
            print(f"Driver error: {e}")

        # Processes
        try:
            procs = []
            for proc in psutil.process_iter(['name', 'memory_percent', 'cpu_percent']):
                try:
                    procs.append(proc.info)
                except:
                    pass
            result['procs'] = sorted(
                procs, key=lambda x: x['memory_percent'], reverse=True)[:8]
        except Exception as e:
            print(f"Process error: {e}")

        return result

    # =========================
    # UI UPDATE
    # =========================
    def _update_ui(self, data):
        try:
            # Health gauge
            if 'health_score' in data:
                score = data['health_score']
                health = data['health']
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

            # Reboot intelligence panel
            if 'anomalies' in data:
                a = data['anomalies']
                score = a['reboot_score']
                status = a['reboot_status']

                # Update reboot gauge
                gauge_color = ACCENT_GREEN if score < 30 else ACCENT_WARN if score < 60 else ACCENT_RED
                self.reboot_gauge.update_value(score, status)

                # Update status label color
                label_color = ACCENT_GREEN if score < 30 else ACCENT_WARN if score < 60 else ACCENT_RED
                self.reboot_status_label.configure(
                    text=f"{'✓' if score < 30 else '⚠'} {status}",
                    text_color=label_color
                )

                # Update reboot text panel
                if not self._reboot_ignored:
                    self.reboot_text.configure(state="normal")
                    self.reboot_text.delete("1.0", "end")

                    # Critical anomalies
                    for msg in a['anomalies']['critical']:
                        self.reboot_text.insert("end", f"🔴 {msg}\n")

                    # Warning anomalies
                    for msg in a['anomalies']['warning']:
                        self.reboot_text.insert("end", f"🟡 {msg}\n")

                    if not a['anomalies']['critical'] and not a['anomalies']['warning']:
                        self.reboot_text.insert("end", "✓ No issues detected\n")

                    # Score breakdown
                    if a['score_breakdown']:
                        self.reboot_text.insert("end", "\n─── Why this score? ───\n")
                        for reason, pts in a['score_breakdown']:
                            self.reboot_text.insert("end", f"  +{pts}  {reason}\n")

                    # Recommendations
                    if a['recommendations']:
                        self.reboot_text.insert("end", "\n─── Recommendations ───\n")
                        for r in a['recommendations']:
                            self.reboot_text.insert("end", f"  → {r}\n")

                    self.reboot_text.configure(state="disabled")

                # Show/hide reboot button based on score
                if score >= 30 and not self._reboot_ignored:
                    self.reboot_btn.configure(state="normal")
                    self.ignore_btn.configure(state="normal")
                elif not self._reboot_ignored:
                    self.reboot_btn.configure(state="disabled")
                    self.ignore_btn.configure(state="disabled")

            # Boot time
            if 'boot_time' in data:
                self.boot_label.configure(text=f"{data['boot_time']} sec")
                self.boot_sub.configure(text="Based on last boot summary")

            # Threat detection
            if 'suspicious' in data:
                suspicious = data['suspicious']
                self.threat_text.configure(state="normal")
                self.threat_text.delete("1.0", "end")
                if len(suspicious) == 0:
                    self.threat_text.insert("end", "✓ No threats detected\n\n  All processes are safe.")
                else:
                    for _, row in suspicious.iterrows():
                        self.threat_text.insert(
                            "end",
                            f"⚠ {row['name']}\n  CPU: {row['cpu_percent']}% | RAM: {round(row['memory_percent'], 2)}%\n\n"
                        )
                self.threat_text.configure(state="disabled")

            # Drivers
            if 'drivers' in data:
                drivers = data['drivers']
                flagged = [d for d in drivers if d['flag'] in ['DISABLED', 'MISSING PATH']]
                self.driver_text.configure(state="normal")
                self.driver_text.delete("1.0", "end")
                self.driver_text.insert("end", f"Total : {len(drivers)}  |  Flagged : {len(flagged)}\n\n")
                for d in flagged[:8]:
                    self.driver_text.insert("end", f"⚠ {d['display_name'][:28]}\n  {d['flag']}\n\n")
                if not flagged:
                    self.driver_text.insert("end", "✓ All drivers healthy")
                self.driver_text.configure(state="disabled")

            # Processes
            if 'procs' in data:
                self.process_text.configure(state="normal")
                self.process_text.delete("1.0", "end")
                for p in data['procs']:
                    self.process_text.insert(
                        "end",
                        f"► {p['name'][:25]}\n  RAM: {round(p['memory_percent'], 2)}% | CPU: {p['cpu_percent']}%\n\n"
                    )
                self.process_text.configure(state="disabled")

            self.last_update.configure(
                text=f"Last updated: {datetime.datetime.now().strftime('%H:%M:%S')}"
            )

        except Exception as e:
            print(f"UI error: {e}")

    def on_closing(self):
        self.running = False
        self.destroy()

if __name__ == "__main__":
    app = AIBootDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()