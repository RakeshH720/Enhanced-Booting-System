import threading
import time
import psutil
import os

def cpu_stress(duration=30):
    """Spike CPU usage"""
    print(f"Starting CPU stress for {duration} seconds...")
    stop = threading.Event()
    
    def burn():
        while not stop.is_set():
            x = 0
            for i in range(100000):
                x += i * i
    
    threads = []
    for _ in range(4):
        t = threading.Thread(target=burn)
        t.daemon = True
        t.start()
        threads.append(t)
    
    time.sleep(duration)
    stop.set()
    print("CPU stress stopped.")

def ram_stress(duration=30):
    """Spike RAM usage"""
    print(f"Starting RAM stress for {duration} seconds...")
    data = []
    try:
        for _ in range(200):
            data.append(' ' * 1024 * 1024)
            time.sleep(0.05)
        time.sleep(duration)
    finally:
        del data
        print("RAM stress stopped.")

def inject_suspicious_process():
    """Add fake suspicious process to boot log"""
    import pandas as pd
    import datetime

    LOG_FILE = "data/boot_log.csv"
    suspicious_processes = [
        {"name": "keylogger32.exe", "cpu_percent": 45.0, "memory_percent": 8.5, "status": "running"},
        {"name": "cryptominer.exe", "cpu_percent": 89.0, "memory_percent": 12.0, "status": "running"},
        {"name": "unknown_service.exe", "cpu_percent": 34.0, "memory_percent": 6.2, "status": "running"},
        {"name": "suspicious_task.exe", "cpu_percent": 56.0, "memory_percent": 9.8, "status": "running"},
    ]

    rows = []
    for p in suspicious_processes:
        p["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows.append(p)

    df = pd.DataFrame(rows)
    if os.path.exists(LOG_FILE):
        df.to_csv(LOG_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(LOG_FILE, index=False)

    print(f"Injected {len(rows)} suspicious processes into boot log.")
    print("Refresh dashboard to see threats detected.")

def clear_suspicious():
    """Remove injected suspicious processes from log"""
    import pandas as pd

    LOG_FILE = "data/boot_log.csv"
    suspicious_names = [
        "keylogger32.exe", "cryptominer.exe",
        "unknown_service.exe", "suspicious_task.exe"
    ]

    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        df = df[~df['name'].isin(suspicious_names)]
        df.to_csv(LOG_FILE, index=False)
        print("Suspicious processes cleared from log.")

def full_demo(duration=40):
    """
    Full demo sequence:
    1. Inject suspicious processes
    2. Stress CPU + RAM together
    3. Auto clean after duration
    """
    print("\n" + "="*50)
    print("DEMO MODE STARTING")
    print("Watch your dashboard now!")
    print("="*50 + "\n")

    # Step 1 — inject threats
    inject_suspicious_process()
    print("\nWait 6 seconds for dashboard to refresh...\n")
    time.sleep(6)

    # Step 2 — stress system
    print("Now stressing CPU and RAM...")
    cpu_thread = threading.Thread(target=cpu_stress, args=(duration,))
    ram_thread = threading.Thread(target=ram_stress, args=(duration,))
    cpu_thread.start()
    ram_thread.start()

    print(f"Stress running for {duration} seconds...")
    print("Watch health score drop and reboot score rise on dashboard!\n")

    cpu_thread.join()
    ram_thread.join()

    # Step 3 — clean up
    print("\nStress complete. Cleaning up...")
    clear_suspicious()
    print("Dashboard should recover in next refresh.")
    print("\nDEMO COMPLETE.")

if __name__ == "__main__":
    print("\nAI E-Booting System - Demo Simulator")
    print("="*40)
    print("1. CPU Stress only")
    print("2. RAM Stress only")
    print("3. Inject suspicious processes")
    print("4. Clear suspicious processes")
    print("5. Full demo (recommended)")
    print("="*40)

    choice = input("Choose option (1-5): ").strip()

    if choice == "1":
        cpu_stress(30)
    elif choice == "2":
        ram_stress(30)
    elif choice == "3":
        inject_suspicious_process()
    elif choice == "4":
        clear_suspicious()
    elif choice == "5":
        full_demo(40)
    else:
        print("Invalid choice.")