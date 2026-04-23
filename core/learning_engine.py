import json
import os
from collections import defaultdict

LOG_FILE = "data/action_log.jsonl"
LEARNED_IGNORE_FILE = "data/learned_ignore.json"

MIN_ATTEMPTS = 3          
MIN_SUCCESS_RATE = 0.3    
MAX_LOG_LINES = 1000      # Prevents memory bloat

def analyze_and_learn():
    """Reads historical logs and generates a dynamic ignore list."""
    if not os.path.exists(LOG_FILE):
        return {"status": "no_data", "learned_processes": []}

    process_stats = defaultdict(lambda: {"attempts": 0, "successes": 0})

    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-MAX_LOG_LINES:]
            
            # Protect against empty file edge case
            if not lines:
                return {"status": "no_data", "learned_processes": []}
                
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    actions = entry.get("actions_taken", [])
                    
                    for action in actions:
                        proc_name = action.get("process", "").lower()
                        if not proc_name:
                            continue
                            
                        process_stats[proc_name]["attempts"] += 1
                        if action.get("success", False):
                            process_stats[proc_name]["successes"] += 1
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"Learning Engine Error: {e}")
        return {"status": "error"}

    new_ignore_list = []
    for proc, stats in process_stats.items():
        if stats["attempts"] >= MIN_ATTEMPTS:
            success_rate = stats["successes"] / stats["attempts"]
            if success_rate < MIN_SUCCESS_RATE:
                new_ignore_list.append(proc.lower()) # Enforce lowercase

    try:
        os.makedirs(os.path.dirname(LEARNED_IGNORE_FILE), exist_ok=True)
        with open(LEARNED_IGNORE_FILE, "w") as f:
            json.dump({"ignored_processes": new_ignore_list}, f, indent=4)
        
        return {"status": "success", "learned_processes": new_ignore_list}
    except Exception as e:
        return {"status": "error"}

def get_learned_ignore_list():
    """Retrieves the dynamically learned ignore list."""
    if not os.path.exists(LEARNED_IGNORE_FILE):
        return set()
    try:
        with open(LEARNED_IGNORE_FILE, "r") as f:
            data = json.load(f)
            return set(p.lower() for p in data.get("ignored_processes", []))
    except:
        return set()