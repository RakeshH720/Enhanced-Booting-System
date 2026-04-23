import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor
import joblib
import os
import json
from datetime import datetime

SUMMARY_FILE = "data/boot_summary.csv"
THREAT_FILE = "data/threat_log.csv"
META_FILE = "data/retrain_meta.json"
ANOMALY_MODEL = "data/anomaly_model.pkl"
PREDICTOR_MODEL = "data/boot_predictor.pkl"

RETRAIN_AFTER_ROWS = 200
RETRAIN_AFTER_DAYS = 3

def load_meta():
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r') as f:
            return json.load(f)
    return {"last_trained": "2000-01-01", "rows_used": 0}

def save_meta(rows_used):
    with open(META_FILE, 'w') as f:
        json.dump({
            "last_trained": datetime.now().strftime("%Y-%m-%d"),
            "rows_used": rows_used
        }, f)

def should_retrain():
    if not os.path.exists(SUMMARY_FILE):
        print("No data yet. Run boot_logger.py first.")
        return False

    meta = load_meta()
    df = pd.read_csv(SUMMARY_FILE)
    new_rows = len(df) - meta["rows_used"]
    days = (datetime.now() - pd.to_datetime(meta["last_trained"])).days

    print(f"New rows since last train: {new_rows}")
    print(f"Days since last train: {days}")

    if new_rows >= RETRAIN_AFTER_ROWS or days >= RETRAIN_AFTER_DAYS:
        return True

    print("Retraining not needed yet.")
    return False

def train_anomaly_model():
    if not os.path.exists(THREAT_FILE):
        print("No threat log found. Skipping anomaly model.")
        return

    df = pd.read_csv(THREAT_FILE)
    df['cpu_percent'] = pd.to_numeric(df['cpu_percent'], errors='coerce').fillna(0)
    df['memory_percent'] = pd.to_numeric(df['memory_percent'], errors='coerce').fillna(0)

    # Use sliding window — last 1000 rows only
    df = df.tail(1000)

    features = df[['cpu_percent', 'memory_percent']]
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(features)
    joblib.dump(model, ANOMALY_MODEL)
    print(f"Anomaly model trained on {len(df)} rows and saved.")

def train_boot_predictor():
    df = pd.read_csv(SUMMARY_FILE)
    df['avg_cpu'] = pd.to_numeric(df['avg_cpu'], errors='coerce').fillna(0)
    df['avg_mem'] = pd.to_numeric(df['avg_mem'], errors='coerce').fillna(0)
    df['max_cpu'] = pd.to_numeric(df['max_cpu'], errors='coerce').fillna(0)

    # Sliding window
    df = df.tail(1000)
    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour.fillna(12)

    # Simulated boot time based on load
    rng = np.random.default_rng(seed=42)
    df['boot_time'] = (
    10 +
    (df['avg_cpu'] * 0.3) +
    (df['avg_mem'] * 0.2) +
    rng.normal(0, 1, len(df))
)

    features = df[['avg_cpu', 'max_cpu', 'avg_mem', 'active_procs', 'hour']]
    target = df['boot_time']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(features, target)
    joblib.dump(model, PREDICTOR_MODEL)

    predicted = model.predict(features.tail(1))[0]
    print(f"Boot predictor trained. Latest prediction: {round(predicted, 2)} sec")

def run_retrain():
    print("=" * 40)
    print("Retrain Check")
    print("=" * 40)

    if not should_retrain():
        return

    print("\nRetraining models...")
    train_anomaly_model()

    df = pd.read_csv(SUMMARY_FILE)
    train_boot_predictor()
    save_meta(len(df))

    print("\nRetraining complete.")
    print("=" * 40)

if __name__ == "__main__":
    run_retrain()