import json
import os
import threading

STATE_FILE = "data/agent_state.json"
_lock = threading.Lock()

def get_state():
    with _lock:
        if not os.path.exists(STATE_FILE):
            return {"consecutive_failures": 0}
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"consecutive_failures": 0}

def save_state(state):
    with _lock:
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            pass

def increment_failure():
    state = get_state()
    state["consecutive_failures"] = min(state["consecutive_failures"] + 1, 10)
    save_state(state)
    return state["consecutive_failures"]

def reset_failures():
    state = get_state()
    state["consecutive_failures"] = 0
    save_state(state)