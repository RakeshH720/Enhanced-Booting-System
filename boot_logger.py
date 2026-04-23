import psutil
import pandas as pd
import datetime
import os

SUMMARY_FILE = "data/boot_summary.csv"
THREAT_FILE = "data/threat_log.csv"

def get_running_processes():
    processes = []
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            processes.append({
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "name": proc.info['name'],
                "cpu_percent": proc.info['cpu_percent'],
                "memory_percent": round(proc.info['memory_percent'], 2),
                "status": proc.info['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes

def save_smart_logs(processes):
    df = pd.DataFrame(processes)
    df['cpu_percent'] = pd.to_numeric(df['cpu_percent'], errors='coerce').fillna(0)
    df['memory_percent'] = pd.to_numeric(df['memory_percent'], errors='coerce').fillna(0)

    # 1 row summary for ML training
    summary = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_procs": len(df),
        "avg_cpu": round(df["cpu_percent"].mean(), 2),
        "max_cpu": df["cpu_percent"].max(),
        "avg_mem": round(df["memory_percent"].mean(), 2),
        "max_mem": df["memory_percent"].max(),
        "active_procs": len(df[(df["cpu_percent"] > 0.5) | (df["memory_percent"] > 0.5)])
    }
    summary_df = pd.DataFrame([summary])
    summary_df.to_csv(SUMMARY_FILE, mode='a',
                      header=not os.path.exists(SUMMARY_FILE), index=False)

    # Only active processes for threat detection
    threats = df[(df["cpu_percent"] > 0.5) | (df["memory_percent"] > 0.5)].copy()
    if not threats.empty:
        threats.to_csv(THREAT_FILE, mode='a',
                       header=not os.path.exists(THREAT_FILE), index=False)

    print(f"Summary saved. {len(threats)} active processes logged to threat log.")

def run_logger():
    print("Boot Logger started...")
    processes = get_running_processes()
    save_smart_logs(processes)

if __name__ == "__main__":
    run_logger()