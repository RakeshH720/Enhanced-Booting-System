import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.dashboard import AIBootDashboard

if __name__ == "__main__":
    app = AIBootDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()