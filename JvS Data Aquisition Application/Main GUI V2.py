import tkinter as tk
import queue, time
from Telem import TelemetryController
from TelemetryDashboard import *







# ===============================
# device Manager
# ================================



# ======================================================
# MAIN APP
# ======================================================
if __name__ == "__main__":
    root = tk.Tk()
    gui_queue = queue.Queue()
    controller = TelemetryController(gui_queue, root)
    dashboard = TelemetryDashboard(root, controller)

    # Start listeners (UDP/TCP)
    controller.start_listeners()
    if (False):
        dashboard.demo_update()
        dashboard.demo_update_time()
    # Clean exit
    root.protocol("WM_DELETE_WINDOW", controller.stop)

    root.mainloop()


