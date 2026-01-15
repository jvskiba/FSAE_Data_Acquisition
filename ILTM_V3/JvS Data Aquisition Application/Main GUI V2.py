import tkinter as tk
import queue
from Device_Manager import TelemetryController

from dataclasses import asdict
import random
from typing import List

from matplotlib.axes import Axes
#from Telem import *
from Device_Manager import *
import tkinter as tk
from tkinter import Frame, StringVar, ttk
import queue
from tkinter import Button
from GUI_Widgets import *
from Timing_Controller import *




# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController):
        self.root = root
        self.controller = controller

        sectors = [
        Sector(start_gate=1, end_gate=1),
        Sector(start_gate=1, end_gate=2),
        Sector(start_gate=2, end_gate=3),
        ]

        self.timing_controller = TimingController(sectors)

        events = [
            {"gate_id": 2, "timestamp": 200},
            {"gate_id": 3, "timestamp": 500},
            {"gate_id": 1, "timestamp": 1000},
            {"gate_id": 2, "timestamp": 3000},
            {"gate_id": 3, "timestamp": 3500},
            {"gate_id": 1, "timestamp": 5000},
            {"gate_id": 2, "timestamp": 6000},
            {"gate_id": 3, "timestamp": 7400},
            {"gate_id": 1, "timestamp": 8200},
        ]

        for e in events:
            self.timing_controller.record_event(e)
        
        self.gui_elements = []
        self.gui_timing_elements = []
        self.flag_state = "Green"

        root.title("Dashboard Layout")
        root.geometry("1400x900")
        root.minsize(1200, 800)

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
        #self.build_time_ui(frame_f)
        #self.build_time_ui_v2(frame_f)
        self.build_vitals2_ui(frame_f)
        self.build_long_plot_ui(frame_g)

        
        # Start queue processing loop
        self.root.after(100, self.process_gui_queue)
        self.root.after(100, self.update_dev_health)

        self.last_update = time.monotonic()

        self.ax: Optional[Axes] = None  # will be set later

    def build_control_ui(self, parent):
        def handle_gate_btn():
            if self.controller.arm_gate:
                arm_gate_btn.config(text="Arm Gate", bg="red")
                self.controller.disarm()
            else:
                arm_gate_btn.config(text="Disarm Gate", bg="green")
                self.controller.arm()

        arm_gate_btn = tk.Button(parent, text="Arm Gate", bg="red", command=handle_gate_btn)
        arm_gate_btn.pack(pady=5)
        ttk.Label(parent, text="Marker:").pack()
        self.marker_entry = ttk.Entry(parent)
        self.marker_entry.pack()
        ttk.Button(
            parent,
            text="Add Marker",
            command=lambda: (self.controller.add_marker(self.marker_entry.get()), self.marker_entry.delete(0, tk.END)),
        ).pack(pady=5)

        ttk.Label(parent, text="Command:").pack()
        self.cmd_entry = ttk.Entry(parent)
        self.cmd_entry.pack()
        ttk.Button(
            parent,
            text="Send Command",
            command=lambda: (self.controller.send_cmd(int(self.cmd_entry.get().strip())), self.cmd_entry.delete(0, tk.END)),
        ).pack(pady=5)

        def handle_log_btn():
            if self.controller.logging:
                start_log_btn.config(text="Start Log", bg="red")
                self.controller.stop_logging()
            else:
                start_log_btn.config(text="Stop Log", bg="green")
                self.controller.start_logging()

        start_log_btn = tk.Button(parent, text="Start Log", bg="red", command=handle_log_btn)
        start_log_btn.pack(pady=5)


        cone_btn = ImageButton(parent, "Cone.png", command=self.controller.log_cone)
        cone_btn.pack(expand=True, pady=5, padx=10)

        cone_btn = ImageButton(parent, "Offtrack.png", text="Off Track", command=self.controller.log_off_track)
        cone_btn.pack(expand=True, pady=5)
        self.flag_state = tk.StringVar(value="Green")
        dropdown = tk.OptionMenu(parent, self.flag_state, *FLAG_STYLES.keys(), command=self.handle_flag)
        dropdown.pack()
        self.flag_widget = FlagWidget(parent, col_names=["Flag"], title="Race Flag", flag="Green")
        self.flag_widget.pack(fill=tk.X, expand=True, pady=5, padx=5)

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
        
        self.gui_elements.append(InfoBox(parent, title="FR Shock", col_name="FR_Shock", initial_value="---", bg_color="grey", fg_color="white"))
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
        self.health_widget = DeviceStatusWidget(parent)
        self.health_widget.pack(padx=10, pady=10)
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
        self.gui_elements.append(VerticalBar(parent, col_names=["TPS"], title="TPS", max_value=100, bar_color="green"))
        self.gui_elements[-1].grid(row=0, column=1, padx=5, pady=10, sticky="nsew")
    
        self.gui_elements.append(VerticalBar(parent, col_names=["BPS"], title="BPS", max_value=100, bar_color="red"))
        self.gui_elements[-1].grid(row=0, column=2, padx=5, pady=10, sticky="nsew")
    
        self.gui_elements.append(VerticalBar(parent, col_names=["CLC"], title="CLC", max_value=100, bar_color="blue"))
        self.gui_elements[-1].grid(row=0, column=3, padx=5, pady=10, sticky="nsew")

        self.gui_elements.append(HorizontalIndicator(parent, col_names=["STR"], title="Steering", min_value=-100, max_value=100))
        self.gui_elements[-1].grid(row=1, column=0, columnspan=4, padx=5, pady=10, sticky="nsew")


    def build_time_ui(self, parent):
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=3)
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        
        self.gui_timing_elements.append(InfoBox(parent, title="Last Time", col_name="LastTime", initial_value="---", bg_color="grey"))
        self.gui_timing_elements[-1].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_timing_elements.append(InfoBox(parent, title="Best Time", col_name="BestTime", initial_value="---", bg_color="grey"))
        self.gui_timing_elements[-1].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.gui_timing_elements.append(InfoBox(parent, title="Avg Time", col_name="AvgTime", initial_value="---", bg_color="grey"))
        self.gui_timing_elements[-1].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_timing_elements.append(InfoBox(parent, title="Delta Time", col_name="DeltaTime", initial_value="---", bg_color="grey"))
        self.gui_timing_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.times_plot = PlotBox(parent, col_names=["INDEX", "LastTime"])
        self.times_plot.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

    
    def build_time_ui_v2(self, parent):
        self.timing_gui = TimingGUI(parent, self.timing_controller)

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
        plot = PlotBox(plot_frame, col_names=["INDEX", "RPM", "VSS", "Gear"])
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


    def build_vitals2_ui(self, parent):
        for c in range(4):
            parent.rowconfigure(c, weight=1)
        for c in range(3):
            parent.columnconfigure(c, weight=1)
        
        self.gui_elements.append(InfoBox(parent, title="GPS Lat", col_name="GPS_Lat", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="GPS Lon", col_name="GPS_Lon", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="GPS Heading", col_name="GPS_Heading", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="GPS Velocity", col_name="GPS_Speed", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Sats", col_name="GPS_Sats", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="", col_name="", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="SNR", col_name="SNR", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="RSSI", col_name="RSSI", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AccelX", col_name="AccelX", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AccelY", col_name="AccelY", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="AccelZ", col_name="AccelZ", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="", col_name="", initial_value="---", bg_color="grey"))
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
                elif kind == "time_data":
                    data = payload
                    self.update_timing(data)
                    
        except queue.Empty:
            pass
    
        # Update only the newest telem_data row if there was one
        if latest_telem or (time.monotonic() - self.last_update) > 1.0:
            self.update(self.controller.signals.get_latest_telem())
            self.last_update = time.monotonic()
    
        # reschedule
        if self.controller.running:
            self.root.after(50, self.process_gui_queue)

    def handle_flag(self, flag):
        self.flag_state = flag
        self.flag_widget.update_data(flag)
        self.controller.change_flag(flag)

    # ------------------------------
    def update(self, row: dict):
        for elmt in self.gui_elements:
            elmt.update_data(row)
            
    def update_timing(self, data: dict):
        for elmt in self.gui_timing_elements:
            elmt.update_data(data)
        self.times_plot.update_data(data)

    def update_dev_health(self):
        self.health_widget.update_data(self.controller.devices)
        if self.controller.running:
            self.root.after(1000, self.update_dev_health)

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
        #global count
        row = {
            "command": 1,
            "timestamp": self.count,
            "RPM": random.randint(800, 12000),
            "MPH": random.randint(0, 150),
            "Gear": random.choice([1, 2, 3, 4, 5, 6]),
            "STR": random.randint(-100, 100),
            "TPS": random.randint(0, 100),
            "BPS": random.randint(0, 100),
            "CLC": random.randint(0, 100),
            "AccelX": random.uniform(-2, 2),
            "AccelY": random.uniform(-2, 2),
            "CLT1": random.randint(60, 110),
            "CLT2": random.randint(60, 110),
            "OilTemp": random.randint(70, 130),
            "AirTemp": random.randint(20, 50),
            "FuelPres": random.randint(30, 60),
            "OilPres": random.randint(20, 80),
            "AFR": random.randint(10, 20),
            "Flag": self.flag_state,
        }
        self.count = self.count + 1
        self.update(row)
        self.controller.logger.log_telemetry(row)
        self.root.after(200, self.demo_update)

    def demo_update_time(self):
        global gui_queue, controller
        row = f"TRIGGER, {random.randint(20, 40)}"
        self.controller.handle_timing(row)
        self.root.after(1000, self.demo_update_time)




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


