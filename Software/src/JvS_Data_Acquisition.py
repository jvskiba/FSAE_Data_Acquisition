import tkinter as tk
import queue
import random
from tkinter import ttk
import queue

from Device_Manager import *
from GUI_Widgets import *
from ConfigManager import *
from FileEditor import *
from LayoutBuilder import *

# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController, configManager: ConfigManager):
        self.root = root
        self.controller = controller
        self.config = configManager.config

        root.title("JvS Data Aquisition App")
        root.geometry("1400x900")
        root.minsize(1200, 800)

        menubar = tk.Menu(root)

        def editConfig():
            new_window = tk.Toplevel(root)
            new_window.title("Config Editor")
            new_window.geometry("800x600")

            editor = FileEditor(new_window)
            editor.open_file("config.json")
            return
        
        def do_option():
            return

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Edit Config", command=editConfig)
        file_menu.add_command(label="Reload Config", command=configManager.load) #TODO: Currently not really working
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)

        # Options Menu
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Settings", command=do_option)
        options_menu.add_command(label="Preferences", command=do_option)

        menubar.add_cascade(label="File", menu=file_menu)
        #menubar.add_cascade(label="Options", menu=options_menu)
        root.config(menu=menubar)

        layout_manager = LayoutManager(root, widget_registry)
        layout_manager.load_layout("layout.json")
        self.gui_elements = layout_manager.get_widgets()
        
        # Start queue processing loop
        self.root.after(100, self.process_gui_queue)
        self.last_update = time.monotonic()

    def build_control_ui(self, parent):
        ttk.Label(parent, text="Marker:").pack()
        self.marker_entry = ttk.Entry(parent)
        self.marker_entry.pack()
        ttk.Button(
            parent,
            text="Add Marker",
            command=lambda: (self.controller.add_marker(self.marker_entry.get()), self.marker_entry.delete(0, tk.END)),
        ).pack(pady=5)

        def send_command():
            cmd = self.cmd_entry.get().strip()
            val = self.cmd_val_entry.get().strip()

            if not cmd or not val:
                print("⚠ Empty input, ignoring")
                return

            try:
                cmd_int = int(cmd)
                val_int = int(val)
            except ValueError:
                print("⚠ Invalid number input")
                return

            self.controller.send_cmd(cmd_int, val_int)

            self.cmd_entry.delete(0, tk.END)
            self.cmd_val_entry.delete(0, tk.END)

        def send_command_wifi():
            cmd = self.cmd_entry_wifi.get().strip()

            if not cmd:
                print("⚠ Empty input, ignoring")
                return

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.config.vehicle_ip, self.config.vehicle_port))

            s.sendall(cmd.encode("utf-8") + b"\n")
            print(s.recv(1024).decode())

            s.close()

            self.cmd_entry_wifi.delete(0, tk.END)

        ttk.Label(parent, text="Command:").pack()
        self.cmd_entry = ttk.Entry(parent)
        self.cmd_entry.pack()
        self.cmd_val_entry = ttk.Entry(parent)
        self.cmd_val_entry.pack()
        ttk.Button(
            parent,
            text="Send Command",
            command=send_command,
        ).pack(pady=5)

        ttk.Label(parent, text="Wifi Command:").pack()
        self.cmd_entry_wifi = ttk.Entry(parent)
        self.cmd_entry_wifi.pack()
        ttk.Button(
            parent,
            text="Send Wifi Command",
            command=send_command_wifi,
        ).pack(pady=5)

    # ------------------------------
    # Queue consumer (thread-safe)
    # ------------------------------
    def process_gui_queue(self):
        latest_telem = None
        try:
            while True:
                kind, payload = self.controller.gui_queue.get_nowait()
                
                if kind == "log":
                    #self.text_console.insert(tk.END, payload + "\n")
                    #self.text_console.see(tk.END)
                    continue
                elif kind == "status":
                    print("!!! Check - GUI Status")
                    #self.status_label.config(text=payload)
                elif kind == "telem_data":
                    # keep only the newest telem row
                    latest_telem = payload
                    
        except queue.Empty:
            pass
    
        # Update only the newest telem_data row if there was one
        if latest_telem or (time.monotonic() - self.last_update) > 1.0:
            self.update(self.controller.signals.get_latest_telem())
            self.last_update = time.monotonic()
    
        # reschedule
        if self.controller.running:
            self.root.after(50, self.process_gui_queue)

    # ------------------------------
    def update(self, row: dict):
        for elmt in self.gui_elements:
            elmt.update_data(row)

    # ------------------------------
    # Optional demo generator
    # ------------------------------
    count = 0
    def demo_update(self):
        self.controller.signals.update("RPM", random.randint(800, 12000))
        self.controller.signals.update("VSS", random.randint(0, 150))
        self.controller.signals.update("Gear", random.choice([1, 2, 3, 4, 5, 6]))
        self.controller.signals.update("STR", random.randint(-100, 100))
        self.controller.signals.update("TPS", random.randint(0, 100))
        self.controller.signals.update("BPS1", random.randint(0, 100))
        self.controller.signals.update("CLC", random.randint(0, 100))
        self.controller.signals.update("AccelX", random.uniform(-2, 2))
        self.controller.signals.update("AccelY", random.uniform(-2, 2))
        self.controller.signals.update("CLT1", random.randint(60, 110))
        self.controller.signals.update("CLT2", random.randint(60, 110))
        self.controller.signals.update("OilTemp", random.randint(70, 130))
        self.controller.signals.update("AirTemp", random.randint(20, 50))
        self.controller.signals.update("FuelPres", random.randint(30, 60))
        self.controller.signals.update("OilPres", random.randint(20, 80))
        self.controller.signals.update("AFR", random.randint(10, 20))
        self.update(self.controller.signals.get_latest_telem())
        root.after(200, self.demo_update)
 




# ======================================================
# MAIN APP
# ======================================================
if __name__ == "__main__":
    root = tk.Tk()
    gui_queue = queue.Queue()
    config_manager = ConfigManager("config.json")
    config = config_manager.config
    controller = TelemetryController(gui_queue, root, config)
    dashboard = TelemetryDashboard(root, controller, config_manager)

    # Start listeners (UDP/TCP)
    controller.start_listeners()
    if (True):
        dashboard.demo_update()
        #dashboard.demo_update_time()
    # Clean exit
    root.protocol("WM_DELETE_WINDOW", controller.stop)

    root.mainloop()


