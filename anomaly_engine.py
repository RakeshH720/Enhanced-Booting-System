import psutil
import datetime

THRESHOLDS = {
    "cpu_critical": 85,
    "cpu_warning": 60,
    "ram_critical": 85,
    "ram_warning": 60,
    "disk_critical": 90,
    "battery_low": 20,
}

def detect_anomalies():
    print("Runtime Anomaly Engine")
    print("=" * 50)

    anomalies = []
    recommendations = []
    reboot_score = 0

    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('C:\\')
    battery = psutil.sensors_battery()

    # CPU check
    if cpu > THRESHOLDS["cpu_critical"]:
        anomalies.append(f"CRITICAL: CPU usage at {cpu}%")
        recommendations.append("Kill heavy processes immediately")
        reboot_score += 30
    elif cpu > THRESHOLDS["cpu_warning"]:
        anomalies.append(f"WARNING: CPU usage at {cpu}%")
        recommendations.append("Monitor CPU usage closely")
        reboot_score += 10

    # RAM check
    if ram.percent > THRESHOLDS["ram_critical"]:
        anomalies.append(f"CRITICAL: RAM usage at {ram.percent}%")
        recommendations.append("Close unused applications")
        reboot_score += 30
    elif ram.percent > THRESHOLDS["ram_warning"]:
        anomalies.append(f"WARNING: RAM usage at {ram.percent}%")
        recommendations.append("Consider closing background apps")
        reboot_score += 10

    # Disk check
    if disk.percent > THRESHOLDS["disk_critical"]:
        anomalies.append(f"CRITICAL: Disk usage at {disk.percent}%")
        recommendations.append("Free up disk space immediately")
        reboot_score += 20

    # Battery check
    if battery:
        if not battery.power_plugged and battery.percent < THRESHOLDS["battery_low"]:
            anomalies.append(f"WARNING: Battery at {battery.percent}%")
            recommendations.append("Plug in charger soon")
            reboot_score += 10

    # Detect crashed/zombie processes
    crashed = []
    for proc in psutil.process_iter(['name', 'status']):
        try:
            if proc.info['status'] == psutil.STATUS_ZOMBIE:
                crashed.append(proc.info['name'])
                reboot_score += 5
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if crashed:
        anomalies.append(f"ZOMBIE PROCESSES: {', '.join(crashed[:5])}")
        recommendations.append("Restart affected applications")

    # High memory processes
    print("\nTop 5 Memory-Hungry Processes:")
    procs = []
    for proc in psutil.process_iter(['name', 'memory_percent', 'cpu_percent']):
        try:
            procs.append(proc.info)
        except:
            pass

    procs = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:5]
    for p in procs:
        print(f"  {p['name']} | RAM: {round(p['memory_percent'], 2)}% | CPU: {p['cpu_percent']}%")

    # Results
    print("\nAnomalies Detected:")
    if anomalies:
        for a in anomalies:
            print(f"  {a}")
    else:
        print("  No anomalies detected. System is running fine.")

    print("\nRecommendations:")
    if recommendations:
        for r in recommendations:
            print(f"  → {r}")
    else:
        print("  → System is stable. No action needed.")

    print(f"\nReboot Score: {reboot_score}/100")
    if reboot_score >= 60:
        print("REBOOT RECOMMENDED")
    elif reboot_score >= 30:
        print("REBOOT SUGGESTED — system under stress")
    else:
        print("NO REBOOT NEEDED — system is stable")

    print("=" * 50)

if __name__ == "__main__":
    detect_anomalies()