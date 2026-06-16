import tkinter as tk
import queue
import random
from typing import List
from matplotlib.axes import Axes
from tkinter import Frame, StringVar, ttk
import queue
from tkinter import Button

from Device_Manager import *
from GUI_Widgets import *
from ConfigManager import *
from FileEditor import *

# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController, configManager: ConfigManager):
        self.root = root
        self.controller = controller
        self.config = configManager.config

        self.gui_elements = []

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

        for i in range(3):
            root.rowconfigure(i, weight=1, uniform="row")
        for j in range(4):
            root.columnconfigure(j, weight=1, uniform="col")

        # Frames
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=4)
        root.columnconfigure(2, weight=4)
        root.columnconfigure(3, weight=2)
        root.rowconfigure(0, weight=2)
        root.rowconfigure(1, weight=2)
        root.rowconfigure(2, weight=1)
        frame_a = tk.Frame(root)
        frame_b = tk.Frame(root)
        frame_c = tk.Frame(root)
        frame_d = tk.Frame(root)
        frame_e = tk.Frame(root)
        frame_f = tk.Frame(root)
        frame_g = tk.Frame(root)

        frame_a.grid(row=0, column=0, rowspan=2, sticky="nsew")
        frame_b.grid(row=0, column=1, sticky="nsew")
        frame_c.grid(row=0, column=2, sticky="nsew")
        frame_d.grid(row=0, column=3, rowspan=2, sticky="nsew")
        frame_e.grid(row=1, column=1, sticky="nsew")
        frame_f.grid(row=1, column=2, sticky="nsew")
        frame_g.grid(row=2, column=0, columnspan=4, sticky="nsew")

        self.build_control_ui(frame_a)
        self.build_main_telem_ui(frame_b)
        self.build_vitals_ui(frame_c)
        self.build_log_ui(frame_d)
        self.build_driver_ui(frame_e)
        self.build_vitals2_ui(frame_f)
        #self.build_small_plot_ui(frame_f)
        self.build_long_plot_ui(frame_g)
        
        # Start queue processing loop
        self.root.after(100, self.process_gui_queue)

        self.last_update = time.monotonic()

        self.ax: Optional[Axes] = None  # will be set later

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

    def build_main_telem_ui(self, parent):
        for c in range(3):
            parent.rowconfigure(c, weight=1)
            parent.columnconfigure(c, weight=1)
        self.gui_elements.append(InfoBox(parent, title="RPM", col_name="RPM", initial_value="-----", bg_color="grey"))
        self.gui_elements[-1].grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Gear", col_name="Gear", initial_value="-", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="MPH", col_name="VSS", initial_value="--", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Fuel Con", col_name="FuelCon", initial_value="-----", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="CLT", col_name="CLT1", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AFR", col_name="AFR", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

    def build_vitals_ui(self, parent):
        for c in range(4):
            parent.rowconfigure(c, weight=1)
        for c in range(3):
            parent.columnconfigure(c, weight=1)
        
        self.gui_elements.append(InfoBox(parent, title="FR Shock", col_name="BS1", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="FL Shock", col_name="FL_Shock", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="RR Shock", col_name="RR_Shock", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="RL Shock", col_name="RL_Shock", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Oil Pres", col_name="OilPres", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="MAP", col_name="MAP", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="Fuel Pres", col_name="FuelPres", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Bat Pres", col_name="BatV", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Eng Temp", col_name="CLT1", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Rad Out", col_name="CLT2", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="Oil Temp", col_name="OilTemp", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Air Temp", col_name="MAT", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=2, padx=10, pady=10, sticky="nsew")

    def build_log_ui(self, parent):
        #self.health_widget = DeviceStatusWidget(parent)
        #self.health_widget.pack(padx=10, pady=10)
        self.text_console = tk.Text(parent, height=20, width=80)
        self.text_console.pack(fill="both", expand=True)

    def build_driver_ui(self, parent):      
        # Configure parent grid
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=6)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=6)
        parent.columnconfigure(2, weight=6)
        parent.columnconfigure(3, weight=6)
    
        # G-Circle plot on the left
        self.gui_elements.append(GCirclePlot(parent, col_names=["AccelX", "AccelY"], max_g=2.0, rings=4, bg="white"))
        self.gui_elements[-1].grid(row=0, column=0, padx=5, pady=10, sticky="nsew")
    
        # Bars on the right
        self.gui_elements.append(VerticalBar(parent, col_name="TPS", title="TPS", max_value=100, bar_color="green"))
        self.gui_elements[-1].grid(row=0, column=1, padx=5, pady=10, sticky="nsew")
    
        self.gui_elements.append(VerticalBar(parent, col_name="BPS1", title="BPS1", max_value=100, bar_color="red"))
        self.gui_elements[-1].grid(row=0, column=2, padx=5, pady=10, sticky="nsew")
    
        self.gui_elements.append(VerticalBar(parent, col_name="BPS2", title="BPS2", max_value=100, bar_color="blue"))
        self.gui_elements[-1].grid(row=0, column=3, padx=5, pady=10, sticky="nsew")

        self.gui_elements.append(HorizontalIndicator(parent, col_name="STR", title="Steering", min_value=-100, max_value=100))
        self.gui_elements[-1].grid(row=1, column=0, columnspan=4, padx=5, pady=10, sticky="nsew")

    def build_long_plot_ui(self, parent: tk.Widget):
        # Container frame for layout
        container: Frame = tk.Frame(parent)
        container.pack(fill="both", expand=True)

        # Left frame: buttons
        btn_frame: Frame = tk.Frame(container)
        btn_frame.pack(side="left", fill="y", padx=5, pady=5)

        # Right frame: plot
        plot_frame: Frame = tk.Frame(container)
        plot_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)

        # Create PlotBox in right frame
        plot = PlotBox(plot_frame, col_names=["AGE", "RPM", "VSS", "Gear"]) #TODO: convert time to seconds ago or smth
        plot.pack(fill="both", expand=True)
        self.gui_elements.append(plot)

        # Track active button
        active_btn: StringVar = tk.StringVar(value="All Time")

        # Button callback
        def set_plot_window(label: str, seconds: int):
            # Update plot rolling window
            if seconds == 0:
                plot.keep_all = True
            else:
                plot.keep_all = False
                plot.max_seconds = seconds

            # Update button highlights
            active_btn.set(label)
            for child in btn_frame.winfo_children():
                if isinstance(child, Button):  # type guard for Pylance
                    if child["text"] == label:
                        child.config(bg="lightblue")
                    else:
                        child.config(bg="SystemButtonFace")

        # Create buttons
        times: List[tuple[str, int]] = [("All Time", 0), ("5s", 5), ("10s", 10), ("30s", 30), ("60s", 60)]
        for label, secs in times:
            btn: Button = tk.Button(btn_frame, text=label, command=lambda l=label, s=secs: set_plot_window(l, s))
            btn.pack(fill="x", pady=2)

        # Initialize highlight
        set_plot_window("All Time", 0)

    def build_small_plot_ui(self, parent: tk.Widget):
        plot = PlotBox(
            parent,
            col_names=["TIME_RX", "RPM"],
            compact=True
        )
        plot.pack(fill="both", expand=True)

        self.gui_elements.append(plot)


    def build_vitals2_ui(self, parent):
        for c in range(4):
            parent.rowconfigure(c, weight=1)
        for c in range(3):
            parent.columnconfigure(c, weight=1)
        
        self.gui_elements.append(InfoBox(parent, title="Yaw", col_name="Yaw", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Pitch", col_name="Pitch", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="Roll", col_name="Roll", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="VelNorth", col_name="VelNorth", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="PosLat", col_name="PosLat", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="PosLong", col_name="PosLong", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="PosAlt", col_name="PosAlt", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="VelEast", col_name="VelEast", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AccelX", col_name="AccelX", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AccelY", col_name="AccelY", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="AccelZ", col_name="AccelZ", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="VelDown", col_name="VelDown", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=2, padx=10, pady=10, sticky="nsew")

    # ------------------------------
    # Queue consumer (thread-safe)
    # ------------------------------
    def process_gui_queue(self):
        latest_telem = None
        try:
            while True:
                kind, payload = self.controller.gui_queue.get_nowait()
                
                if kind == "log":
                    self.text_console.insert(tk.END, payload + "\n")
                    self.text_console.see(tk.END)
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
    def update_plot(self):
        if self.ax is None:
            return
        
        self.ax.clear()
        # Example: just draw axes/title for now
        self.ax.set_ylabel("Value")
        self.ax.set_xlabel("Time")
        self.ax.set_title("Telemetry Plot")
        self.ax.grid(True)
        self.root.after(1000, self.update_plot)

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


