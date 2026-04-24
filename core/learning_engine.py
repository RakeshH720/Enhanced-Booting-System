import json
import os
import pandas as pd
from collections import defaultdict

# ==========================================
# 📁 FILE PATHS
# ==========================================
LOG_FILE = "data/action_log.jsonl"
LEARNED_IGNORE_FILE = "data/learned_ignore.json"
HEALTH_LOG = "data/health_log.csv"
ADAPTIVE_THRESHOLDS_FILE = "data/adaptive_thresholds.json"

# ==========================================
# ⚙️ CONFIG
# ==========================================
MIN_ATTEMPTS = 3
MIN_SUCCESS_RATE = 0.3
MAX_LOG_LINES = 1000

# ==========================================
# 🛑 ACTION LEARNING (EXISTING)
# ==========================================
def analyze_and_learn():
    if not os.path.exists(LOG_FILE):
        return {"status": "no_data", "learned_processes": []}

    process_stats = defaultdict(lambda: {"attempts": 0, "successes": 0})

    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-MAX_LOG_LINES:]
            if not lines:
                return {"status": "no_data", "learned_processes": []}

            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    for action in entry.get("actions_taken", []):
                        proc_name = action.get("process", "").lower()
                        if not proc_name:
                            continue

                        process_stats[proc_name]["attempts"] += 1
                        if action.get("success", False):
                            process_stats[proc_name]["successes"] += 1
                except json.JSONDecodeError:
                    pass
    except Exception:
        return {"status": "error"}

    new_ignore_list = [
        proc.lower()
        for proc, stats in process_stats.items()
        if stats["attempts"] >= MIN_ATTEMPTS
        and (stats["successes"] / stats["attempts"]) < MIN_SUCCESS_RATE
    ]

    try:
        os.makedirs(os.path.dirname(LEARNED_IGNORE_FILE), exist_ok=True)
        with open(LEARNED_IGNORE_FILE, "w") as f:
            json.dump({"ignored_processes": new_ignore_list}, f, indent=4)

        return {"status": "success", "learned_processes": new_ignore_list}
    except Exception:
        return {"status": "error"}


def get_learned_ignore_list():
    if not os.path.exists(LEARNED_IGNORE_FILE):
        return set()
    try:
        with open(LEARNED_IGNORE_FILE, "r") as f:
            return set(p.lower() for p in json.load(f).get("ignored_processes", []))
    except Exception:
        return set()

# ==========================================
# 🧠 BEHAVIOR LEARNING (NEW)
# ==========================================
def update_adaptive_thresholds():
    if not os.path.exists(HEALTH_LOG):
        return {"status": "no_data"}

    try:
        df = pd.read_csv(HEALTH_LOG).tail(500)

        # 🔒 Safety check (important)
        if df.empty or 'cpu_percent' not in df.columns or 'ram_used_percent' not in df.columns:
            return {"status": "invalid_data"}

        avg_cpu = df['cpu_percent'].mean()
        avg_ram = df['ram_used_percent'].mean()

        thresholds = {
            "cpu_warn": round(max(60.0, avg_cpu * 1.5), 1),
            "cpu_crit": round(max(85.0, avg_cpu * 2.0), 1),
            "ram_warn": round(max(70.0, avg_ram * 1.2), 1),
            "ram_crit": round(max(85.0, avg_ram * 1.5), 1),
            "learned_baseline_cpu": round(avg_cpu, 1),
            "learned_baseline_ram": round(avg_ram, 1),
            "status_message": "System adapts to usage patterns."
        }

        os.makedirs(os.path.dirname(ADAPTIVE_THRESHOLDS_FILE), exist_ok=True)

        with open(ADAPTIVE_THRESHOLDS_FILE, "w") as f:
            json.dump(thresholds, f, indent=4)

        return {"status": "success", "thresholds": thresholds}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_adaptive_thresholds():
    default_thresholds = {
        "cpu_warn": 60.0,
        "cpu_crit": 85.0,
        "ram_warn": 70.0,
        "ram_crit": 85.0,
        "learned_baseline_cpu": 0.0,
        "learned_baseline_ram": 0.0,
        "status_message": "Default static thresholds active."
    }

    if not os.path.exists(ADAPTIVE_THRESHOLDS_FILE):
        return default_thresholds

    try:
        with open(ADAPTIVE_THRESHOLDS_FILE, "r") as f:
            data = json.load(f)
            return {**default_thresholds, **data}
    except Exception:
        return default_thresholds