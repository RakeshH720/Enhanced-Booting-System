import psutil
import datetime

def get_system_health():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('C:\\')

    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = temps.get('coretemp', [{}])[0].get('current', 'N/A') if temps else 'N/A'
    except AttributeError:
        cpu_temp = 'N/A'

    battery = psutil.sensors_battery()
    battery_percent = battery.percent if battery else 'N/A'
    plugged = battery.power_plugged if battery else 'N/A'

    health_data = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_percent": cpu,
        "ram_used_percent": ram.percent,
        "ram_available_gb": round(ram.available / (1024**3), 2),
        "disk_used_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "cpu_temp": cpu_temp,
        "battery_percent": battery_percent,
        "plugged_in": plugged
    }

    return health_data

def calculate_health_score(data):
    score = 100

    if data['cpu_percent'] > 80:
        score -= 25
    elif data['cpu_percent'] > 50:
        score -= 10

    if data['ram_used_percent'] > 85:
        score -= 25
    elif data['ram_used_percent'] > 60:
        score -= 10

    if data['disk_used_percent'] > 90:
        score -= 20
    elif data['disk_used_percent'] > 70:
        score -= 10

    if isinstance(data['battery_percent'], float):
        if data['battery_percent'] < 20:
            score -= 15
        elif data['battery_percent'] < 40:
            score -= 5

    return max(score, 0)

def run_health_monitor():
    print("System Health Monitor\n" + "="*40)
    data = get_system_health()

    print(f"CPU Usage      : {data['cpu_percent']}%")
    print(f"RAM Usage      : {data['ram_used_percent']}%")
    print(f"RAM Available  : {data['ram_available_gb']} GB")
    print(f"Disk Usage     : {data['disk_used_percent']}%")
    print(f"Disk Free      : {data['disk_free_gb']} GB")
    print(f"CPU Temp       : {data['cpu_temp']}")
    print(f"Battery        : {data['battery_percent']}%")
    print(f"Plugged In     : {data['plugged_in']}")
    print("="*40)

    score = calculate_health_score(data)
    print(f"System Health Score: {score}/100")

    if score >= 80:
        print("Status: System is healthy")
    elif score >= 50:
        print("Status: System needs attention")
    else:
        print("Status: WARNING - Poor system health, reboot recommended")

if __name__ == "__main__":
    run_health_monitor()