import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor
import joblib
import os

MODEL_FILE = "data/anomaly_model.pkl"
LOG_FILE = "data/boot_log.csv"

# Known Windows system processes — never flag these
SYSTEM_PROCESSES = {
    'system idle process', 'system', 'registry', 'smss.exe', 'csrss.exe',
    'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe',
    'explorer.exe', 'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
    'wmiprvse.exe', 'audiodg.exe', 'wudfhost.exe', 'runtimebroker.exe',
    'searchhost.exe', 'searchindexer.exe', 'spoolsv.exe', 'msmpseng.exe',
    'nissrv.exe', 'securityhealthservice.exe', 'sgrmbroker.exe',
    'memcompression', 'ntoskrnl.exe', 'conhost.exe', 'dllhost.exe',
    'ctfmon.exe', 'dashost.exe', 'localbridge.exe', 'lsaiso.exe',
    'msmpeng.exe', 'winlogon.exe', 'wlanext.exe', 'wlms.exe',
}

def load_data():
    if not os.path.exists(LOG_FILE):
        print("No boot log found. Run boot_logger.py first.")
        return None
    df = pd.read_csv(LOG_FILE)
    df['cpu_percent'] = pd.to_numeric(df['cpu_percent'], errors='coerce').fillna(0)
    df['memory_percent'] = pd.to_numeric(df['memory_percent'], errors='coerce').fillna(0)
    return df

def build_process_profile(df):
    """Build a profile of each process based on historical behavior."""
    profile = df.groupby('name').agg(
        appearance_count=('name', 'count'),
        avg_cpu=('cpu_percent', 'mean'),
        max_cpu=('cpu_percent', 'max'),
        avg_ram=('memory_percent', 'mean'),
        max_ram=('memory_percent', 'max'),
    ).reset_index()

    total_scans = df['timestamp'].nunique()
    profile['frequency_ratio'] = profile['appearance_count'] / max(total_scans, 1)

    return profile

def is_legitimate(row, profile_df):
    """
    Determine if a process is legitimate based on learned behavior.
    Returns True if process is known/legitimate.
    """
    name = str(row['name']).lower()

    # Always trust system processes
    if name in SYSTEM_PROCESSES:
        return True

    # Check learned profile
    match = profile_df[profile_df['name'].str.lower() == name]
    if not match.empty:
        freq = match.iloc[0]['frequency_ratio']
        # If process appears in more than 10% of scans, it's a regular process
        if freq > 0.1:
            return True

    return False

def train_anomaly_detector(df):
    features = df[['cpu_percent', 'memory_percent']].fillna(0)
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )
    model.fit(features)
    joblib.dump(model, MODEL_FILE)
    return model

def detect_threats(df, model):
    features = df[['cpu_percent', 'memory_percent']].fillna(0)
    predictions = model.predict(features)
    df = df.copy()
    df['anomaly'] = predictions
    df['threat_level'] = df['anomaly'].apply(
        lambda x: 'SUSPICIOUS' if x == -1 else 'NORMAL'
    )

    # Build process profile from history
    profile = build_process_profile(df)

    suspicious = df[df['threat_level'] == 'SUSPICIOUS'].copy()

    # Filter out legitimate processes using learned behavior
    suspicious['is_legit'] = suspicious.apply(
        lambda row: is_legitimate(row, profile), axis=1
    )
    real_threats = suspicious[~suspicious['is_legit']]

    print(f"Total processes scanned : {len(df)}")
    print(f"Flagged by ML           : {len(suspicious)}")
    print(f"Filtered as legitimate  : {len(suspicious) - len(real_threats)}")
    print(f"Real threats            : {len(real_threats)}")

    if len(real_threats) > 0:
        print("\nReal Threats Detected:")
        top = real_threats[['name', 'cpu_percent', 'memory_percent']]\
            .drop_duplicates(subset='name')\
            .sort_values('cpu_percent', ascending=False)\
            .head(10)
        for _, row in top.iterrows():
            print(f"  ⚠ {row['name']} | CPU: {row['cpu_percent']}% | RAM: {round(row['memory_percent'],2)}%")
    else:
        print("\n✓ No real threats detected.")

    # Return full df with threat info
    df['is_legit'] = df.apply(lambda row: is_legitimate(row, profile), axis=1)
    df.loc[df['is_legit'], 'threat_level'] = 'NORMAL'

    return df

def train_boot_predictor(df):
    df = df.copy()
    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour.fillna(12)
    df['cpu_rolling'] = df['cpu_percent'].rolling(3, min_periods=1).mean()
    df['ram_rolling'] = df['memory_percent'].rolling(3, min_periods=1).mean()

    df['simulated_boot_time'] = (
        10 +
        (df['cpu_rolling'] * 0.3) +
        (df['ram_rolling'] * 0.2) +
        np.random.normal(0, 1, len(df))
    )

    features = df[['cpu_percent', 'memory_percent', 'hour', 'cpu_rolling', 'ram_rolling']]
    target = df['simulated_boot_time']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(features, target)

    predicted = model.predict(features[:1])[0]
    print(f"\nPredicted next boot time: {round(predicted, 2)} seconds")

    joblib.dump(model, "data/boot_predictor.pkl")
    print("Boot predictor saved.")
    return model

def run_ml():
    print("ML Engine Started")
    print("=" * 50)
    df = load_data()
    if df is None:
        return

    anomaly_model = train_anomaly_detector(df)
    detect_threats(df, anomaly_model)
    train_boot_predictor(df)

    print("\n" + "=" * 50)
    print("ML Engine Complete.")

if __name__ == "__main__":
    run_ml()