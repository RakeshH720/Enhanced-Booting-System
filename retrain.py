import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor
import joblib
import os
import json
from datetime import datetime

# =========================
# FILE PATHS
# =========================
SUMMARY_FILE = "data/boot_summary.csv"
THREAT_FILE = "data/threat_log.csv"
META_FILE = "data/retrain_meta.json"
ANOMALY_MODEL = "data/anomaly_model.pkl"
PREDICTOR_MODEL = "data/boot_predictor.pkl"

RETRAIN_AFTER_ROWS = 200
RETRAIN_AFTER_DAYS = 3

os.makedirs("data", exist_ok=True)

# =========================
# META HANDLING
# =========================
def load_meta():
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"last_trained": "2000-01-01", "rows_used": 0}

def save_meta(rows_used):
    with open(META_FILE, 'w') as f:
        json.dump({
            "last_trained": datetime.now().strftime("%Y-%m-%d"),
            "rows_used": rows_used
        }, f)

# =========================
# RETRAIN CHECK
# =========================
def should_retrain():
    if not os.path.exists(SUMMARY_FILE):
        print("No data yet. Run boot_logger.py first.")
        return False

    df = pd.read_csv(SUMMARY_FILE)

    # Fix 1 — empty file guard
    if df.empty:
        print("Summary file is empty. Skipping.")
        return False

    meta = load_meta()

    # Fix 3 — negative rows fix
    new_rows = max(0, len(df) - meta.get("rows_used", 0))

    # Fix 4 — safe date parsing
    try:
        last_trained = pd.to_datetime(meta["last_trained"])
    except:
        last_trained = pd.to_datetime("2000-01-01")

    days = (datetime.now() - last_trained).days

    print(f"New rows since last train: {new_rows}")
    print(f"Days since last train: {days}")

    if new_rows >= RETRAIN_AFTER_ROWS or days >= RETRAIN_AFTER_DAYS:
        return True

    print("Retraining not needed yet.")
    return False

# =========================
# ANOMALY MODEL
# =========================
def train_anomaly_model():
    if not os.path.exists(THREAT_FILE):
        print("No threat log found. Skipping anomaly model.")
        return

    df = pd.read_csv(THREAT_FILE)

    # Fix 5 — empty threat log guard
    if df.empty:
        print("Threat log empty. Skipping anomaly model.")
        return

    df['cpu_percent'] = pd.to_numeric(df['cpu_percent'], errors='coerce').fillna(0)
    df['memory_percent'] = pd.to_numeric(df['memory_percent'], errors='coerce').fillna(0)

    df = df.tail(1000)

    features = df[['cpu_percent', 'memory_percent']]

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )

    model.fit(features)
    joblib.dump(model, ANOMALY_MODEL)

    print(f"Anomaly model trained on {len(df)} rows.")

# =========================
# BOOT PREDICTOR
# =========================
def train_boot_predictor():
    df = pd.read_csv(SUMMARY_FILE)

    # Fix 1 — empty file guard
    if df.empty:
        print("Summary file is empty. Skipping predictor.")
        return

    # Clean columns
    df['avg_cpu'] = pd.to_numeric(df['avg_cpu'], errors='coerce').fillna(0)
    df['max_cpu'] = pd.to_numeric(df['max_cpu'], errors='coerce').fillna(0)
    df['avg_mem'] = pd.to_numeric(df['avg_mem'], errors='coerce').fillna(0)
    df['max_mem'] = pd.to_numeric(df['max_mem'], errors='coerce').fillna(0)

    # Fix 2 — active_procs column might not exist
    if 'active_procs' not in df.columns:
        df['active_procs'] = 0
    df['active_procs'] = pd.to_numeric(df['active_procs'], errors='coerce').fillna(0)

    # Use real boot time only
    if 'boot_time' not in df.columns:
        print("No real boot_time available. Skipping predictor training.")
        return

    df = df[df['boot_time'] > 0].dropna(subset=['boot_time'])

    if len(df) < 50:
        print(f"Not enough valid boot_time rows ({len(df)}). Need 50. Skipping predictor.")
        return

    df = df.tail(1000)
    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour.fillna(12)
    df['cpu_spike'] = df['max_cpu'] - df['avg_cpu']

    features = df[['avg_cpu', 'max_cpu', 'avg_mem', 'max_mem',
                   'active_procs', 'hour', 'cpu_spike']]
    target = df['boot_time']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(features, target)
    joblib.dump(model, PREDICTOR_MODEL)

    predicted = model.predict(features.tail(1))[0]
    print(f"Boot predictor trained. Latest prediction: {round(predicted, 2)} sec")

# =========================
# MAIN
# =========================
def run_retrain():
    print("=" * 40)
    print("Retrain Check")
    print("=" * 40)

    if not should_retrain():
        return

    print("\nRetraining models...")

    train_anomaly_model()
    train_boot_predictor()

    df = pd.read_csv(SUMMARY_FILE)
    save_meta(len(df))

    print("\nRetraining complete.")
    print("=" * 40)

if __name__ == "__main__":
    run_retrain()