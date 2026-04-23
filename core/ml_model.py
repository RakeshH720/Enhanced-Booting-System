import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import os

ANOMALY_MODEL = "data/anomaly_model.pkl"
THREAT_FILE = "data/threat_log.csv"

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

def load_threat_data():
    if not os.path.exists(THREAT_FILE):
        return None
    df = pd.read_csv(THREAT_FILE)
    if df.empty:
        return None
    df['cpu_percent'] = pd.to_numeric(df['cpu_percent'], errors='coerce').fillna(0)
    df['memory_percent'] = pd.to_numeric(df['memory_percent'], errors='coerce').fillna(0)
    return df

def build_process_profile(df):
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
    name = str(row['name']).lower()

    if name in SYSTEM_PROCESSES:
        return True

    match = profile_df[profile_df['name'].str.lower() == name]
    if not match.empty:
        if match.iloc[0]['frequency_ratio'] > 0.1:
            return True

    return False

def detect_threats(df, model):
    if df is None or df.empty:
        return None

    features = df[['cpu_percent', 'memory_percent']].fillna(0)
    predictions = model.predict(features)
    df = df.copy()
    df['anomaly'] = predictions
    df['threat_level'] = df['anomaly'].apply(
        lambda x: 'SUSPICIOUS' if x == -1 else 'NORMAL'
    )

    profile = build_process_profile(df)
    df['is_legit'] = df.apply(lambda row: is_legitimate(row, profile), axis=1)
    df.loc[df['is_legit'], 'threat_level'] = 'NORMAL'

    return df

def load_model():
    if os.path.exists(ANOMALY_MODEL):
        return joblib.load(ANOMALY_MODEL)
    return None