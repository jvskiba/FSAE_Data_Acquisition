import tkinter as tk
from tkinter import ttk
import queue, threading, socket, sys, time, csv, random
from datetime import datetime, UTC
from dataclasses import make_dataclass, asdict
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque
import math

# =====================
# Element Classes
# =====================
class ParentWidget(tk.Frame):
    def __init__(self, parent, title="Parent", col_names=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.parent = parent
        self.title = title
        self.col_names = col_names
    
    def update_data(self, data):
        """Placeholder method to update widget with data"""
        pass

class InfoBox(ParentWidget):
    def __init__(self, parent, title="", col_name="", initial_value="---", bg_color="gray", fg_color="white", **kwargs):
        super().__init__(parent, title=title, col_names=[col_name], **kwargs)
        self.config(bg=bg_color)

        # Attach labels to self.frame, not self
        self.title_label = tk.Label(self, text=title, fg=fg_color, bg=bg_color, font=("Arial", 10, "bold"))
        self.title_label.pack(anchor="nw", padx=5, pady=(5, 0))
        
        self.value_label = tk.Label(self, text=initial_value, fg=fg_color, bg=bg_color, font=("Arial", 24, "bold"), width=len(initial_value), anchor="center")
        self.value_label.pack(anchor="center", expand=True, padx=5, pady=5)

    def update_data(self, data):
        if self.col_names[0] in data:
            self.value_label.config(text=f'{data[self.col_names[0]]}')


class PlotBox(ParentWidget):
    def __init__(self, parent, title="", col_names=None, colors=None,
                 y_limits=None, keep_all=True, max_points=500, **kwargs):
        super().__init__(parent, title=title, col_names=col_names, **kwargs)
        
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.title = title
        self.col_names = col_names
        self.x_data = []
        self.y_data = {name: [] for name in col_names[1:]}

        # Colors
        self.colors = colors if colors else ["blue", "red", "green", "orange", "purple"][:len(col_names)-1]

        # Y-limits: can be None (autoscale per line), single tuple (all same), or list of tuples
        if y_limits is None:
            self.y_limits = [None] * (len(col_names) - 1)
        elif isinstance(y_limits[0], (int, float)):
            # single min/max for all lines
            self.y_limits = [y_limits] * (len(col_names) - 1)
        else:
            self.y_limits = y_limits
        if len(self.y_limits) != len(col_names) - 1:
            raise ValueError("Length of y_limits must match number of y columns")

        self.keep_all = keep_all
        self.max_points = max_points
        self.lines = {}

        self.ax.set_title(title)
        self.ax.set_xlabel(col_names[0])
        self.ax.set_ylabel("Values")
        self.ax.grid(True)

        # Bind resize
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        w, h = event.width, event.height
        dpi = self.fig.get_dpi()
        self.fig.set_size_inches(w / dpi, h / dpi)
        self.canvas.draw()

    def update_data(self, data):
        if self.col_names[0] == "INDEX":
            if len(self.x_data) < 1:
                self.x_data.append(0)
            else:
                self.x_data.append(self.x_data[-1] + 1)
        else:
            self.x_data.append(data[self.col_names[0]])
        for name in self.col_names[1:]:
            self.y_data[name].append(data[name])

        # Apply rolling buffer if needed
        if not self.keep_all:
            self.x_data = self.x_data[-self.max_points:]
            for name in self.col_names[1:]:
                self.y_data[name] = self.y_data[name][-self.max_points:]

        self._draw_plot()

    def _draw_plot(self):
        self.ax.clear()
        self.ax.set_title(self.title)
        self.ax.set_xlabel(self.col_names[0])
        self.ax.set_ylabel("Values")
        self.ax.grid(True)

        # Plot each line
        for idx, name in enumerate(self.col_names[1:]):
            y_vals = self.y_data[name]
            self.ax.plot(self.x_data, y_vals, color=self.colors[idx], label=name)

            # Y-limits
            lim = self.y_limits[idx]
            if lim is not None:
                self.ax.set_ylim(lim)
            # else autoscale happens automatically per line

        # Legend top-right, semi-transparent
        self.ax.legend(loc="upper right", framealpha=0.3)
        self.canvas.draw()



class GCirclePlot(ParentWidget):
    def __init__(self, parent, title="", col_names=None, max_g=2.0, rings=4, trail_length=100, **kwargs):
        super().__init__(parent, title=title, col_names=col_names, **kwargs)

        self.max_g = max_g
        self.rings = rings
        self.trail_length = trail_length

        # Store trail as deque (fast FIFO)
        self.trail_x = deque(maxlen=trail_length)
        self.trail_y = deque(maxlen=trail_length)

        # Setup matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(4, 4))
        self.ax.set_aspect("equal")
        self.ax.set_xlim(-max_g, max_g)
        self.ax.set_ylim(-max_g, max_g)

        # Draw reference lines
        self._draw_reference()

        # Plot objects: point + trail
        (self.point,) = self.ax.plot(0, 0, "ro")
        (self.trail_line,) = self.ax.plot([], [], "b-", alpha=0.6)

        # Embed into Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _draw_reference(self):
        """Draw concentric circles + cross lines"""
        self.ax.axhline(0, color="black", lw=0.8)  # X-axis
        self.ax.axvline(0, color="black", lw=0.8)  # Y-axis

        for r in range(1, self.rings + 1):
            radius = self.max_g * r / self.rings
            circle = plt.Circle((0, 0), radius, color="gray", fill=False, ls="--", lw=0.7)
            self.ax.add_artist(circle)

        self.ax.set_xlabel("Lateral G")
        self.ax.set_ylabel("Longitudinal G")      

    def _on_resize(self, event):
        size = min(self.winfo_width(), self.winfo_height())
        self.config(width=size, height=size)
        self._draw_background()
        self._redraw_points()

    def update_data(self, data):
        x = data[self.col_names[0]]
        y = data[self.col_names[1]]
        # Add new point to buffer
        self.trail_x.append(x)
        self.trail_y.append(y)

        # Update trail and point
        self.point.set_data([x], [y])
        self.trail_line.set_data(self.trail_x, self.trail_y)

        self.canvas.draw_idle()


class VerticalBar(ParentWidget):
    def __init__(self, parent, title="", col_names=None, max_value=100, bar_color="green", **kwargs):
        super().__init__(parent, title=title, col_names=col_names, **kwargs)

        self.max_value = max_value
        self.bar_color = bar_color
        self.current_value = 0

        # Title at the top
        self.title_label = tk.Label(self, text=title, font=("Arial", 10, "bold"))
        self.title_label.pack(pady=(0, 2))

        # Canvas expands with frame
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=1, highlightbackground="black")
        self.canvas.pack(fill="both", expand=True)

        # Value label at the bottom
        self.value_label = tk.Label(self, text="0", font=("Arial", 10))
        self.value_label.pack(pady=(2, 0))

        # Redraw bar whenever size changes
        self.canvas.bind("<Configure>", self._on_resize)

        # Create bar rect placeholder
        self.bar = self.canvas.create_rectangle(0, 0, 0, 0, fill=self.bar_color)

    def _on_resize(self, event):
        """Redraw bar when canvas is resized"""
        self._draw_bar()

    def _draw_bar(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        value = self.current_value

        # Clamp
        value = max(0, min(value, self.max_value))

        # Scale
        fill_height = (value / self.max_value) * h
        y_top = h - fill_height

        # Update rectangle
        self.canvas.coords(self.bar, 5, y_top, w - 5, h)

    def update_data(self, data):
        """Update bar height and numeric label"""
        self.current_value = data[self.col_names[0]]
        self._draw_bar()
        self.value_label.config(text=f"{self.current_value:.1f}")

class HorizontalIndicator(ParentWidget):
    def __init__(self, parent, title="STR", col_names=None, min_value=-540, max_value=540,
                 bar_color="lightgray", line_color="blue", midline_color="black", **kwargs):
        super().__init__(parent, title=title, col_names=col_names, **kwargs)

        self.min_value = min_value
        self.max_value = max_value
        self.line_color = line_color
        self.midline_color = midline_color

        # Title and value labels
        self.title_label = tk.Label(self, text=title, font=("Arial", 10, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

        self.value_label = tk.Label(self, text="0", font=("Arial", 10))
        self.value_label.grid(row=1, column=0, sticky="w")

        # Canvas for bar + indicator line
        self.canvas = tk.Canvas(self, height=40, bg="white", highlightthickness=1, highlightbackground="black")
        self.canvas.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=5, pady=5)

        # Background bar
        self.bar = self.canvas.create_rectangle(0, 15, 200, 25, fill=bar_color, outline="")

        # Midline at 0 (center)
        self.midline = self.canvas.create_line(100, 5, 100, 35, fill=midline_color, dash=(3,2))

        # Indicator line
        self.line = self.canvas.create_line(100, 10, 100, 30, fill=line_color, width=2)

        # Make responsive
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas.bind("<Configure>", self._resize_bar)

    def _resize_bar(self, event):
        """Resize the bar and midline when canvas resizes"""
        self.canvas.coords(self.bar, 0, event.height/2 - 5, event.width, event.height/2 + 5)
        # Move midline to center
        mid_x = event.width / 2
        self.canvas.coords(self.midline, mid_x, 0, mid_x, event.height)
        # Update indicator position
        self._update_line(getattr(self, "current_value", 0))

    def set_value(self, value):
        """Update the indicator line and value display"""
        value = max(self.min_value, min(self.max_value, value))  # clamp
        self.current_value = value
        self.value_label.config(text=f"{value:.1f}")
        self._update_line(value)

    def _update_line(self, value):
        """Update line position based on value (centered at 0)"""
        width = self.canvas.winfo_width()
        if width <= 0:
            return
        # Normalize around center (0 at midline)
        norm = (value - self.min_value) / (self.max_value - self.min_value)
        x = norm * width
        self.canvas.coords(self.line, x, 0, x, self.canvas.winfo_height())

    def update_data(self, data):
        self.set_value(data[self.col_names[0]])




# ======================================================
# CONTROLLER: All logic, networking, state
# ======================================================
class TelemetryController:
    def __init__(self, gui_queue, root, config_file="can_config.csv"):
        self.gui_queue = gui_queue
        self.root = root
        self.running = True
        self.arm_gate = False
        self.latest_telem_data = None
        self.data_log = []
        self.timing_log = []

        # Config
        self.HOST = "0.0.0.0"
        self.GATE_PORT = 5000
        self.UDP_PORT = 5002

        # Load CAN config
        signal_names = self.load_config_signals(config_file)
        self.CanRow = self.make_can_row_class(signal_names)

    # ------------------------------
    # Config parsing
    # ------------------------------
    def load_config_signals(self, config_file: str) -> list[str]:
        try:
            with open(config_file, newline="") as f:
                reader = csv.DictReader(f)
                return [row["Name"] for row in reader]
        except FileNotFoundError:
            print(f"Config file {config_file} not found. Using defaults.")
            return ["timestamp", "RPM", "MPH", "Gear", "STR", "TPS", "BPS", "CLT1", "CLT2", "OilTemp", "AirTemp", "FuelPres", "OilPres"]

    def make_can_row_class(self, signal_names: list[str]):
        fields = [("timestamp", float)] + [(name, float) for name in signal_names if name != "timestamp"]
        return make_dataclass("CanRow", fields)

    def parse_row(self, line: str):
        try:
            parts = line.strip().split(",")
            values = [float(x) if x not in ("NaN", "nan") else float("nan") for x in parts]
            return self.CanRow(*values)
        except Exception as e:
            print("Parse error:", e, "for line:", line)
            return None

    # ------------------------------
    # Gate Controls
    # ------------------------------
    def arm(self):
        self.arm_gate = True
        self.log("Gate Armed")
        self.gui_queue.put(("status", "Gate Armed"))

    def disarm(self):
        self.arm_gate = False
        self.log("Gate Disarmed")
        self.gui_queue.put(("status", "Gate Disarmed"))

    def add_marker(self, text: str):
        if text:
            now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
            self.data_log.append([now, "Marker", None, text])
            self.log(f"Marker added: {text}")

    def log_cone(self):
        self.log("Cone Hit")
        #self.gui_queue.put(("status", "Gate Armed"))

    def log_off_track(self):
        self.log("Off track")
        #self.gui_queue.put(("status", "Gate Disarmed"))

    # ------------------------------
    # Logging & Queue
    # ------------------------------
    def log(self, message):
        if self.running:
            self.gui_queue.put(("log", message))

    def stop(self):
        self.running = False
        self.log("Exiting app...")
        # root.destroy() will be called by main thread via WM_DELETE_WINDOW binding
        self.root.after(0, self.root.destroy)
        sys.exit(0)

    def handle_timing(self, data):
        self.timing_log.append(data)
        vals = self.timing_log
        row = {
            "LastTime": vals[-1] if vals else 0,
            "BestTime": min(vals) if vals else 0,
            "AvgTime": sum(vals) / len(vals) if vals else 0,
            "DeltaTime": vals[-1] if  vals else 0
        }
        print(row["LastTime"])
        self.gui_queue.put(("time_data", row))

    # ------------------------------
    # Networking
    # ------------------------------
    def gate_listener(self):
        """TCP listener for gate."""
        while self.running:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((self.HOST, self.GATE_PORT))
                    s.listen(1)
                    self.log(f"[TCP] Listening on {self.HOST}:{self.GATE_PORT}")

                    conn, addr = s.accept()
                    with conn:
                        self.log(f"[TCP] Connected by {addr}")
                        while self.running:
                            data = conn.recv(1024)
                            if not data:
                                self.log("[TCP] Connection closed")
                                break
                            handle_timing(data.decode(errors='ignore'))
                            self.log(f"[TCP] {data.decode(errors='ignore')}")
            except Exception as e:
                if not self.running: break
                self.log(f"[TCP] Error: {e}, retrying in 2s...")
                time.sleep(2)

    def udp_listener(self):
        """UDP listener for telemetry."""
        while self.running:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((self.HOST, self.UDP_PORT))
                    self.log(f"[UDP] Listening on {self.HOST}:{self.UDP_PORT}")
                    while self.running:
                        data, addr = s.recvfrom(1024)
                        line = data.decode(errors="ignore")
                        row = self.parse_row(line)
                        if row:
                            self.latest_telem_data = row
                            self.gui_queue.put(("data", row))
            except Exception as e:
                if not self.running: break
                self.log(f"[UDP] Error: {e}, retrying in 2s...")
                time.sleep(2)

    def start_listeners(self):
        threading.Thread(target=self.gate_listener, daemon=True).start()
        threading.Thread(target=self.udp_listener, daemon=True).start()


# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController):
        self.root = root
        self.controller = controller
        self.gui_elements = []
        self.gui_timing_elements = []

        root.title("Dashboard Layout")
        root.geometry("1400x900")

        for i in range(3):
            root.rowconfigure(i, weight=1, uniform="row")
        for j in range(4):
            root.columnconfigure(j, weight=1, uniform="col")

        # Frames
        
        """ frame_a = tk.Frame(root, bg="lightblue")
        frame_b = tk.Frame(root, bg="lightgreen")
        frame_c = tk.Frame(root, bg="lightcoral")
        frame_d = tk.Frame(root, bg="khaki")
        frame_e = tk.Frame(root, bg="plum")
        frame_f = tk.Frame(root, bg="lightblue")
        frame_g = tk.Frame(root, bg="lightgreen") """

        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.columnconfigure(2, weight=2)
        root.columnconfigure(3, weight=1)
        root.rowconfigure(0, weight=2)
        root.rowconfigure(1, weight=4)
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
        self.build_time_ui(frame_f)
        self.build_long_plot_ui(frame_g)

        
        # Start queue processing loop
        self.root.after(50, self.process_gui_queue)

    def build_control_ui(self, parent):
        ttk.Button(parent, text="Arm Gate", command=self.controller.arm).pack(pady=5)
        ttk.Button(parent, text="Disarm Gate", command=self.controller.disarm).pack(pady=5)
        self.status_label = ttk.Label(parent, text="Gate Disarmed")
        self.status_label.pack(pady=5)
        ttk.Label(parent, text="Marker:").pack()
        self.marker_entry = ttk.Entry(parent)
        self.marker_entry.pack()
        ttk.Button(
            parent,
            text="Add Marker",
            command=lambda: (self.controller.add_marker(self.marker_entry.get()), self.marker_entry.delete(0, tk.END)),
        ).pack(pady=5)
        ttk.Button(parent, text="Cone", command=self.controller.log_cone).pack(pady=5)
        ttk.Button(parent, text="Off Track", command=self.controller.log_off_track).pack(pady=5)

    def build_main_telem_ui(self, parent):
        for c in range(3):
            parent.rowconfigure(c, weight=1)
            parent.columnconfigure(c, weight=1)
        self.gui_elements.append(InfoBox(parent, title="RPM", col_name="RPM", initial_value="-----", bg_color="grey"))
        self.gui_elements[-1].grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Gear", col_name="Gear", initial_value="-", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="MPH", col_name="MPH", initial_value="--", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Fuel Con", col_name="FuelCon", initial_value="--", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="CLT", col_name="CLT1", initial_value="--", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="AFR", col_name="AFR", initial_value="--", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

    def build_vitals_ui(self, parent):
        for c in range(4):
            parent.rowconfigure(c, weight=1)
        for c in range(3):
            parent.columnconfigure(c, weight=1)
        
        self.gui_elements.append(InfoBox(parent, title="EGT1", col_name="EGT1", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="EGT2", col_name="EGT2", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="EGT3", col_name="EGT3", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="EGT4", col_name="EGT4", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Oil Pres", col_name="OilPres", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="MAP", col_name="MAP", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="Fuel Pres", col_name="FuelPres", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Bat Pres", col_name="VLT", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=1, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Eng Temp", col_name="CLT1", initial_value="---", bg_color="grey", fg_color="white"))
        self.gui_elements[-1].grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Rad Out", col_name="RadTemp", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=1, column=2, padx=10, pady=10, sticky="nsew")
        
        self.gui_elements.append(InfoBox(parent, title="Oil Temp", col_name="OilTemp", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=2, column=2, padx=10, pady=10, sticky="nsew")

        self.gui_elements.append(InfoBox(parent, title="Air Temp", col_name="MAT", initial_value="---", bg_color="grey"))
        self.gui_elements[-1].grid(row=3, column=2, padx=10, pady=10, sticky="nsew")

    def build_log_ui(self, parent):
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
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=3)
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
        self.times_plot.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

    def build_long_plot_ui(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.gui_elements.append(PlotBox(parent, col_names=["timestamp", "RPM", "MPH"]))
        self.gui_elements[-1].grid(row=0, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")

    # ------------------------------
    # Queue consumer (thread-safe)
    # ------------------------------
    def process_gui_queue(self):
        try:
            while True:
                kind, payload = self.controller.gui_queue.get_nowait()
                if kind == "log":
                    self.text_console.insert(tk.END, payload + "\n")
                    self.text_console.see(tk.END)
                elif kind == "status":
                    self.status_label.config(text=payload)
                elif kind == "telem_data":
                    row = payload
                    # Convert dataclass to dict if needed
                    if hasattr(row, "__dataclass_fields__"):
                        data = asdict(row)
                    elif isinstance(row, dict):
                        data = row
                    else:
                        data = row.__dict__
                    self.update(data)
                elif kind == "time_data":
                    data = payload
                    self.update_timing(data)
                    
        except queue.Empty:
            pass
        # reschedule
        if self.controller.running:
            self.root.after(50, self.process_gui_queue)

    # ------------------------------
    def update(self, row: dict):
        for elmt in self.gui_elements:
            elmt.update_data(row)
            
    def update_timing(self, data: dict):
        for elmt in self.gui_timing_elements:
            elmt.update_data(data)
        self.times_plot.update_data(data)


    # ------------------------------
    def update_plot(self):
        self.ax.clear()
        # Example: just draw axes/title for now
        self.ax.set_ylabel("Value")
        self.ax.set_xlabel("Time")
        self.ax.set_title("Telemetry Plot")
        self.ax.grid(True)
        self.canvas.draw()

    # ------------------------------
    # Optional demo generator
    # ------------------------------
    count = 0
    def demo_update(self):
        #global count
        row = {
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
        }
        self.count = self.count + 1
        self.update(row)
        self.root.after(200, self.demo_update)

    def demo_update_time(self):
        global gui_queue, controller
        row = {
            "lapTime": random.randint(20, 40),
        }
        controller.handle_timing(random.randint(20, 40))
        #gui_queue.put(("time_data", row))
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
    dashboard.demo_update()
    dashboard.demo_update_time()
    # Clean exit
    root.protocol("WM_DELETE_WINDOW", controller.stop)

    root.mainloop()
