import sys
import io
import datetime
import threading
import time
import math
import psutil
import joblib
import os
import pandas as pd
import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from core.anomaly_engine import detect_anomalies

# Core imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.health_monitor import get_system_health, calculate_health_score
from core.driver_analyzer import analyze_drivers
from core.ml_model import load_threat_data, detect_threats, load_model

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

plt.rcParams['figure.facecolor'] = '#0d1117'
plt.rcParams['axes.facecolor'] = '#161b22'
plt.rcParams['axes.edgecolor'] = '#30363d'
plt.rcParams['text.color'] = '#8b949e'
plt.rcParams['axes.labelcolor'] = '#8b949e'
plt.rcParams['xtick.color'] = '#8b949e'
plt.rcParams['ytick.color'] = '#8b949e'
plt.rcParams['grid.color'] = '#21262d'

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


class GaugeCanvas(ctk.CTkFrame):
    def __init__(self, parent, title, color, **kwargs):
        super().__init__(parent, fg_color="#161b22", corner_radius=10,
                         border_width=1, border_color="#30363d", **kwargs)
        self.color = color
        self._last_value = -1
        self._arc = None
        self._value_text = None
        self._sub_text = None

        self.canvas = ctk.CTkCanvas(self, bg="#161b22",
                                     highlightthickness=0, width=220, height=160)
        self.canvas.pack(pady=(8, 0))

        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(pady=(2, 8))

        self.canvas.after(100, self._draw_background)

    def _draw_background(self):
        self.canvas.create_arc(20, 10, 200, 150, start=0, extent=180,
                                style="arc", outline="#21262d", width=18)
        self._value_text = self.canvas.create_text(
            110, 110, text="--", font=("Arial", 28, "bold"), fill="white"
        )
        self._sub_text = self.canvas.create_text(
            110, 135, text="", font=("Arial", 8), fill="#8b949e"
        )
        self._arc = self.canvas.create_arc(
            20, 10, 200, 150, start=180, extent=0,
            style="arc", outline=self.color, width=18
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


class AIBootDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI-Based E-Booting Optimization System")
        self.geometry("1300x800")
        self.resizable(True, True)
        self.configure(fg_color="#0d1117")
        self.running = True

        self.cpu_history = [0] * 30
        self.ram_history = [0] * 30

        self._anomaly_model = None
        self._predictor_model = None
        self._driver_cache = None
        self._driver_last_scan = 0

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
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from retrain import run_retrain
            silent(run_retrain)
        except Exception as e:
            print(f"Retrain check error: {e}")

        self.after(0, self.start_refresh_thread)

    def build_ui(self):
        # Title Bar
        title_frame = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=0, height=55)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)

        ctk.CTkLabel(
            title_frame,
            text="⚡ AI-Based E-Booting Optimization System",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#58a6ff"
        ).pack(side="left", padx=20, pady=15)

        ctk.CTkLabel(
            title_frame, text="● LIVE",
            font=ctk.CTkFont(size=12), text_color="#3fb950"
        ).pack(side="right", padx=20)

        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=12, pady=10)

        # Left column
        left = ctk.CTkFrame(main, fg_color="transparent", width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        # Gauges
        gauge_frame = ctk.CTkFrame(left, fg_color="transparent")
        gauge_frame.pack(fill="x")

        self.health_gauge = GaugeCanvas(gauge_frame, "Health Score", "#3fb950")
        self.health_gauge.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self.reboot_gauge = GaugeCanvas(gauge_frame, "Reboot Score", "#f0883e")
        self.reboot_gauge.pack(side="left", fill="both", expand=True, padx=(4, 0))

        # Boot time card
        boot_card = ctk.CTkFrame(left, fg_color="#161b22", corner_radius=10,
                                  border_width=1, border_color="#30363d")
        boot_card.pack(fill="x", pady=8)

        ctk.CTkLabel(boot_card, text="Predicted Boot Time",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkFrame(boot_card, fg_color="#30363d", height=1).pack(fill="x", padx=10)

        self.boot_label = ctk.CTkLabel(boot_card, text="-- sec",
                                        font=ctk.CTkFont(size=36, weight="bold"),
                                        text_color="#58a6ff")
        self.boot_label.pack(pady=(8, 2))
        self.boot_sub = ctk.CTkLabel(boot_card, text="Loading...",
                                      font=ctk.CTkFont(size=11), text_color="#8b949e")
        self.boot_sub.pack(pady=(0, 10))

        # CPU / RAM stats
        stats_frame = ctk.CTkFrame(left, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 8))

        self.cpu_stat = self._make_stat(stats_frame, "CPU", "0%", "#f0883e")
        self.cpu_stat.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self.ram_stat = self._make_stat(stats_frame, "RAM", "0%", "#58a6ff")
        self.ram_stat.pack(side="left", fill="both", expand=True, padx=(4, 0))

        # Threat panel
        threat_card = ctk.CTkFrame(left, fg_color="#161b22", corner_radius=10,
                                    border_width=1, border_color="#30363d")
        threat_card.pack(fill="both", expand=True)

        ctk.CTkLabel(threat_card, text="🔍 Threat Detection",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkFrame(threat_card, fg_color="#30363d", height=1).pack(fill="x", padx=10)

        self.threat_text = ctk.CTkTextbox(threat_card, fg_color="#0d1117",
                                           text_color="#f0883e",
                                           font=ctk.CTkFont(family="Consolas", size=11),
                                           wrap="word")
        self.threat_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.threat_text.insert("end", "Loading...")
        self.threat_text.configure(state="disabled")

        # Right column
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Graph
        graph_card = ctk.CTkFrame(right, fg_color="#161b22", corner_radius=10,
                                   border_width=1, border_color="#30363d")
        graph_card.pack(fill="both", expand=True, pady=(0, 8))

        ctk.CTkLabel(graph_card, text="📈 Live System Performance",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkFrame(graph_card, fg_color="#30363d", height=1).pack(fill="x", padx=10)

        self.fig = Figure(figsize=(6, 3), dpi=80)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.15)
        self.graph_canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        self._draw_graph()

        # Bottom row
        bottom_row = ctk.CTkFrame(right, fg_color="transparent")
        bottom_row.pack(fill="both", expand=True)

        # Driver panel
        driver_card = ctk.CTkFrame(bottom_row, fg_color="#161b22", corner_radius=10,
                                    border_width=1, border_color="#30363d")
        driver_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ctk.CTkLabel(driver_card, text="🔧 Driver Health",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkFrame(driver_card, fg_color="#30363d", height=1).pack(fill="x", padx=10)

        self.driver_text = ctk.CTkTextbox(driver_card, fg_color="#0d1117",
                                           text_color="#8b949e",
                                           font=ctk.CTkFont(family="Consolas", size=11),
                                           wrap="word")
        self.driver_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.driver_text.insert("end", "Loading...")
        self.driver_text.configure(state="disabled")

        # Process panel
        proc_card = ctk.CTkFrame(bottom_row, fg_color="#161b22", corner_radius=10,
                                  border_width=1, border_color="#30363d")
        proc_card.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(proc_card, text="💾 Top Memory Processes",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#58a6ff").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkFrame(proc_card, fg_color="#30363d", height=1).pack(fill="x", padx=10)

        self.process_text = ctk.CTkTextbox(proc_card, fg_color="#0d1117",
                                            text_color="#58a6ff",
                                            font=ctk.CTkFont(family="Consolas", size=11),
                                            wrap="word")
        self.process_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.process_text.insert("end", "Loading...")
        self.process_text.configure(state="disabled")

        # Bottom bar
        bar = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=0, height=32)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.last_update = ctk.CTkLabel(bar, text="Last updated: --",
                                         font=ctk.CTkFont(size=11), text_color="#8b949e")
        self.last_update.pack(side="left", padx=15, pady=8)
        ctk.CTkLabel(bar, text="Auto-refresh: 15s",
                     font=ctk.CTkFont(size=11), text_color="#8b949e").pack(side="right", padx=15)

    def _make_stat(self, parent, label, value, color):
        frame = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=10,
                              border_width=1, border_color="#30363d")
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                     text_color="#8b949e").pack(pady=(8, 0))
        lbl = ctk.CTkLabel(frame, text=value,
                           font=ctk.CTkFont(size=22, weight="bold"), text_color=color)
        lbl.pack(pady=(0, 8))
        frame.value_label = lbl
        return frame

    def _draw_graph(self):
        self.ax.clear()
        x = list(range(30))
        self.ax.plot(x, self.cpu_history, color='#f0883e', linewidth=2, label='CPU %')
        self.ax.fill_between(x, self.cpu_history, alpha=0.15, color='#f0883e')
        self.ax.plot(x, self.ram_history, color='#58a6ff', linewidth=2, label='RAM %')
        self.ax.fill_between(x, self.ram_history, alpha=0.15, color='#58a6ff')
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, 29)
        self.ax.legend(loc='upper left', fontsize=9,
                       facecolor='#161b22', edgecolor='#30363d')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_title("CPU & RAM Usage (Last 30 readings)",
                          fontsize=10, color='#8b949e', pad=8)
        self.graph_canvas.draw()

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
                    df['max_mem'] = pd.to_numeric(df.get('max_mem', pd.Series([0])), errors='coerce').fillna(0)
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
            result['procs'] = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:8]
        except Exception as e:
            print(f"Process error: {e}")

        return result

    def _update_ui(self, data):
        try:
            if 'health_score' in data:
                score = data['health_score']
                health = data['health']
                cpu = health['cpu_percent']
                ram = health['ram_used_percent']

                self.health_gauge.update_value(score, f"CPU:{cpu}% RAM:{ram}%")

                reboot_score = 0
                if cpu > 85: reboot_score += 30
                elif cpu > 60: reboot_score += 10
                if ram > 85: reboot_score += 30
                elif ram > 60: reboot_score += 10
                r_status = "Stable" if reboot_score < 30 else "Stressed" if reboot_score < 60 else "REBOOT!"
                self.reboot_gauge.update_value(reboot_score, r_status)

                cpu_color = "#3fb950" if cpu < 60 else "#f0883e" if cpu < 85 else "#f85149"
                ram_color = "#3fb950" if ram < 60 else "#f0883e" if ram < 85 else "#f85149"
                self.cpu_stat.value_label.configure(text=f"{cpu}%", text_color=cpu_color)
                self.ram_stat.value_label.configure(text=f"{ram}%", text_color=ram_color)

                self.cpu_history.append(cpu)
                self.cpu_history.pop(0)
                self.ram_history.append(ram)
                self.ram_history.pop(0)
                self._draw_graph()

            if 'boot_time' in data:
                self.boot_label.configure(text=f"{data['boot_time']} sec")
                self.boot_sub.configure(text="Based on last boot summary")

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