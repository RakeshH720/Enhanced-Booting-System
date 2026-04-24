import collections
import psutil
import datetime

# Short term: ~2.5 mins (Responsiveness)
_cpu_short = collections.deque(maxlen=10)
# Long term: ~12.5 mins (Stability/Fatigue)
_cpu_long = collections.deque(maxlen=50)

def get_dual_trend():
    cpu = psutil.cpu_percent(interval=0.2)
    _cpu_short.append(cpu)
    _cpu_long.append(cpu)
    
    return {
        "short_cpu": sum(_cpu_short) / len(_cpu_short) if _cpu_short else cpu,
        "long_cpu": sum(_cpu_long) / len(_cpu_long) if _cpu_long else cpu,
        "current_cpu": cpu
    }

def get_system_health():
    trend = get_dual_trend()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('C:\\')
    
    return {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_percent": round(trend["current_cpu"], 1),
        "ram_used_percent": round(ram.percent, 1),
        "disk_used_percent": round(disk.percent, 1)
    }