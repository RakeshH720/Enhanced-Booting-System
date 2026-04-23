import time
import datetime
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from boot_logger import get_running_processes, save_smart_logs
from health_monitor import get_system_health, calculate_health_score
import pandas as pd

LOG_FILE = "data/health_log.csv"

def log_health():
    health = get_system_health()
    score = calculate_health_score(health)
    health['health_score'] = score
    health['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df = pd.DataFrame([health])
    if os.path.exists(LOG_FILE):
        df.to_csv(LOG_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(LOG_FILE, index=False)

    print(f"[{health['timestamp']}] Health logged — Score: {score}/100")

def run_service():
    print("Background Monitor Service Started...")
    print("Logging every 60 seconds. Press Ctrl+C to stop.\n")
    while True:
        try:
            processes = get_running_processes()
            save_smart_logs(processes)
            log_health()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_service()