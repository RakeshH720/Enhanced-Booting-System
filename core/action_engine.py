import psutil
import time
import os
import json
from core.learning_engine import get_learned_ignore_list

SYSTEM_PROCESSES = {
    'system idle process', 'system', 'registry', 'smss.exe', 'csrss.exe',
    'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe',
    'explorer.exe', 'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
    'wmiprvse.exe', 'audiodg.exe', 'wudfhost.exe', 'runtimebroker.exe',
    'searchhost.exe', 'searchindexer.exe', 'spoolsv.exe', 'msmpseng.exe'
}
SAFE_USER_PROCESSES = {"code.exe", "chrome.exe", "firefox.exe", "msedge.exe", "devenv.exe", "pycharm.exe", "obs64.exe"}

MIN_RAM_PERCENT = 5.0
MIN_CPU_PERCENT = 15.0
COOLDOWN_SECONDS = 60
ACTION_LOG_FILE = "data/action_log.jsonl"
CURRENT_PID = os.getpid()

LAST_CPU_ACTION = 0
LAST_RAM_ACTION = 0

def log_action(action_type, details, impact, success):
    try:
        os.makedirs(os.path.dirname(ACTION_LOG_FILE), exist_ok=True)
        entry = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": action_type,
            "actions_taken": details,
            "impact": impact,
            "batch_success": success
        }
        with open(ACTION_LOG_FILE, "a") as f: f.write(json.dumps(entry) + "\n")
    except: pass

def can_take_action(action_type):
    global LAST_CPU_ACTION, LAST_RAM_ACTION
    now = time.time()
    if action_type == "CPU" and (now - LAST_CPU_ACTION >= COOLDOWN_SECONDS):
        LAST_CPU_ACTION = now; return True
    elif action_type == "RAM" and (now - LAST_RAM_ACTION >= COOLDOWN_SECONDS):
        LAST_RAM_ACTION = now; return True
    return False

def is_safe_process(proc):
    try:
        if proc.pid == CURRENT_PID: return True
        name = proc.name().lower()
        if name in SYSTEM_PROCESSES or name in SAFE_USER_PROCESSES or name in get_learned_ignore_list(): return True
    except: return True
    return False

def terminate_process(pid):
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        if is_safe_process(proc): return {"status": "blocked", "process": name}
        proc.terminate(); proc.wait(timeout=3)
        return {"status": "success", "process": name, "pid": pid}
    except psutil.TimeoutExpired:
        proc.kill(); return {"status": "success", "process": name, "pid": pid}
    except: return {"status": "error"}

def auto_clear_cpu():
    if not can_take_action("CPU"): return {"status": "skipped", "message": "Cooldown active"}
    
    candidates, blocked_actions, actions_taken = [], [], []
    for proc in psutil.process_iter(['pid', 'name']):
        try: proc.cpu_percent(interval=None); candidates.append(proc)
        except: pass
    time.sleep(0.1)
    
    proc_stats = sorted([{'pid': p.pid, 'name': p.name(), 'cpu': p.cpu_percent(interval=None)} 
                         for p in candidates if p.cpu_percent(interval=None) > MIN_CPU_PERCENT], 
                        key=lambda x: x['cpu'], reverse=True)
    
    total_freed = 0.0
    for p in proc_stats[:3]:
        res = terminate_process(p['pid'])
        if res['status'] == 'blocked':
            blocked_actions.append({"process": p['name'], "reason": "safelist"})
            continue
        if res['status'] == 'success':
            total_freed += p['cpu']
            res['freed'] = p['cpu']; res['success'] = True
            actions_taken.append(res)
            
    if blocked_actions: log_action("BLOCKED", blocked_actions, {"note": "Protected"}, False)
    if actions_taken:
        impact = {"total_freed": round(total_freed, 2), "before": {"cpu": 100}, "after": {"cpu": 100 - total_freed}}
        log_action("CPU_CLEAR", actions_taken, impact, True)
        return {"status": "executed", "type": "cpu", "actions": actions_taken, "impact": impact}
    return {"status": "skipped", "message": "No targets found"}

def auto_clear_memory():
    if not can_take_action("RAM"): return {"status": "skipped", "message": "Cooldown active"}
    
    procs = sorted([p.info for p in psutil.process_iter(['pid', 'name', 'memory_percent']) 
                    if p.info['memory_percent'] > MIN_RAM_PERCENT], 
                   key=lambda x: x['memory_percent'], reverse=True)
    
    actions_taken, blocked_actions, total_freed = [], [], 0.0
    for p in procs[:3]:
        res = terminate_process(p['pid'])
        if res['status'] == 'blocked': blocked_actions.append({"process": p['name'], "reason": "safelist"}); continue
        if res['status'] == 'success':
            total_freed += p['memory_percent']
            res['freed'] = round(p['memory_percent'], 2); res['success'] = True
            actions_taken.append(res)

    if blocked_actions: log_action("BLOCKED", blocked_actions, {"note": "Protected"}, False)
    if actions_taken:
        impact = {"total_freed": round(total_freed, 2), "before": {"ram": 100}, "after": {"ram": 100 - total_freed}}
        log_action("RAM_CLEAR", actions_taken, impact, True)
        return {"status": "executed", "type": "ram", "actions": actions_taken, "impact": impact}
    return {"status": "skipped", "message": "No targets found"}

def run_autopilot():
    cpu_res = auto_clear_cpu()
    if cpu_res.get('status') == 'executed':
        return cpu_res

    ram_res = auto_clear_memory()
    if ram_res.get('status') == 'executed':
        return ram_res

    # Pass cooldown messages properly
    if "Cooldown" in cpu_res.get('message', ''):
        return cpu_res
    if "Cooldown" in ram_res.get('message', ''):
        return ram_res

    return {"status": "skipped", "message": "No targets found"}