from dataclasses import asdict
import random
from typing import List

from matplotlib.axes import Axes
from Telem import *
import tkinter as tk
from tkinter import Frame, StringVar, ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue
from PIL import Image, ImageTk
from tkinter import Button


# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController):
        self.root = root
        self.controller = controller
        self.gui_elements = []
        self.gui_timing_elements = []
        self.flag_state = "Green"

        root.title("Dashboard Layout")
        root.geometry("1400x900")

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
        self.build_time_ui(frame_f)
        self.build_long_plot_ui(frame_g)

        
        # Start queue processing loop
        self.root.after(100, self.process_gui_queue)
        self.root.after(100, self.update_dev_health)

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
        
        self.gui_elements.append(InfoBox(parent, title="MPH", col_name="MPH", initial_value="--", bg_color="grey"))
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
        plot = PlotBox(plot_frame, col_names=["timestamp", "RPM", "MPH", "Gear"])
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
                plot.max_points = seconds * 10

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
                    self.status_label.config(text=payload)
                elif kind == "telem_data":
                    # keep only the newest telem row
                    latest_telem = payload
                elif kind == "time_data":
                    data = payload
                    self.update_timing(data)
                    
        except queue.Empty:
            pass
    
        # Update only the newest telem_data row if there was one
        if latest_telem:
            row = latest_telem
            if hasattr(row, "__dataclass_fields__"):
                data = asdict(row)
            elif isinstance(row, dict):
                data = row
            else:
                data = row.__dict__
            self.update(data)
    
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
        self.canvas.draw()
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
    def __init__(self, parent, title="", col_name="", initial_value="----",
                 bg_color="#444444", fg_color="white", corner_radius=25, alpha=0.8,
                 padding=5, warn_min=None, warn_max=None, crit_min=None, crit_max=None, **kwargs):
        super().__init__(parent, title=title, col_names=[col_name], **kwargs)

        self.bg_color = bg_color
        self.fg_color = fg_color
        self.corner_radius = corner_radius
        self.alpha = alpha
        self.padding = padding
        self.title = title
        self.value = initial_value
        self.initial_value=initial_value

        # Warning/Critical thresholds
        self.warn_min = warn_min
        self.warn_max = warn_max
        self.crit_min = crit_min
        self.crit_max = crit_max

        # Create canvas
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self.master["bg"])
        self.canvas.pack(fill="both", expand=True)

        self.background_id = None
        self.title_id = None
        self.value_id = None

        # Bind resize to redraw
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        self._draw_background()
        self._draw_text()

    def _get_bg_color(self):
        """Determine background color based on value thresholds"""
        try:
            val = float(self.value)
        except (ValueError, TypeError):
            return self.bg_color  # Non-numeric values keep normal color

        # Critical overrides warning
        if self.crit_min is not None and val < self.crit_min:
            return "red"
        if self.crit_max is not None and val > self.crit_max:
            return "red"

        if self.warn_min is not None and val < self.warn_min:
            return "yellow"
        if self.warn_max is not None and val > self.warn_max:
            return "yellow"

        return self.bg_color

    def _draw_background(self):
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        r = min(self.corner_radius, w//4, h//4)

        fill_color = self._get_bg_color()
        alpha_hex = f"{int(self.alpha * 255):02x}"
        fill_color = fill_color + alpha_hex if fill_color.startswith("#") else fill_color

        if self.background_id:
            self.canvas.delete(self.background_id)
        self.background_id = self._create_rounded_rect(self.canvas, 0, 0, w, h, r, fill=fill_color, outline="")

    def _draw_text(self):
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)

        # Title font ~10-12% of height
        title_size = max(int(h * 0.12), 8)
        value_size = max(int(h * 0.35), 12)

        # Delete old text
        if self.title_id:
            self.canvas.delete(self.title_id)
        if self.value_id:
            self.canvas.delete(self.value_id)

        # Draw title with padding
        self.title_id = self.canvas.create_text(self.padding, self.padding, anchor="nw",
                                                text=self.title,
                                                fill=self.fg_color,
                                                font=("Arial", title_size, "bold"))

        # Draw value centered, but leave padding from edges
        cx = max(self.padding + 1, w/2)
        cy = max(self.padding + 1, h/2)
        #formatted = f"{float(self.value):.{len(self.initial_value)}g}"
        formatted = self.value
        self.value_id = self.canvas.create_text(cx, cy, anchor="center",
                                                text=formatted,
                                                fill=self.fg_color,
                                                font=("Arial", value_size, "bold"))

    @staticmethod
    def _create_rounded_rect(canvas, x1, y1, x2, y2, r=25, **kwargs):
        points = [
            x1+r, y1,
            x2-r, y1,
            x2, y1,
            x2, y1+r,
            x2, y2-r,
            x2, y2,
            x2-r, y2,
            x1+r, y2,
            x1, y2,
            x1, y2-r,
            x1, y1+r,
            x1, y1
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def update_data(self, data):
        if self.col_names[0] not in data:
            return
        value = data[self.col_names[0]]
        formatted = f"{value:.{len(str(self.value))}g}"
        self.value = formatted
        self._draw_background()
        self._draw_text()



class PlotBox(ParentWidget):
    def __init__(self, parent, title="", col_names=None, colors=None,
                 y_limits=None, keep_all=True, max_points=500, y_labels=None, **kwargs):
        super().__init__(parent, title=title, col_names=col_names, **kwargs)

        if col_names is None:
            return

        self.title = title
        self.col_names = col_names
        self.x_data = []
        self.y_data = {name: [] for name in col_names[1:]}

        # Colors
        self.colors = colors if colors else ["blue", "red", "green", "orange", "purple", "brown"][:len(col_names)-1]

        # Y-limits
        if y_limits is None:
            self.y_limits = [None] * (len(col_names) - 1)
        elif isinstance(y_limits[0], (int, float)):
            self.y_limits = [y_limits] * (len(col_names) - 1)
        else:
            self.y_limits = y_limits
        if len(self.y_limits) != len(col_names) - 1:
            raise ValueError("Length of y_limits must match number of y columns")

        # Y-axis labels
        if y_labels is None:
            self.y_labels = [name for name in col_names[1:]]
        elif isinstance(y_labels, str):
            self.y_labels = [y_labels] * (len(col_names) - 1)
        else:
            self.y_labels = y_labels

        self.keep_all = keep_all
        self.max_points = max_points

        # Create figure and main axes
        self.fig, self.ax = plt.subplots(figsize=(6,4))
        self.axes = [self.ax]  # main axes

        # Create twin axes for additional lines
        for i in range(1, len(col_names)-1):
            twin_ax = self.ax.twinx()
            # offset the spine to avoid overlap
            twin_ax.spines["right"].set_position(("axes", 1 + 0.1*(i-1)))
            self.axes.append(twin_ax)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.ax.set_xlabel(col_names[0])
        self.fig.suptitle(title)

        # Bind resize
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        dpi = self.fig.get_dpi()
        self.fig.set_size_inches(event.width / dpi, event.height / dpi)
        self.fig.tight_layout()
        self.canvas.draw()

    def update_data(self, data):
        if self.col_names[0] == "INDEX":
            self.x_data.append(self.x_data[-1] + 1 if self.x_data else 0)
        else:
            self.x_data.append(data[self.col_names[0]])

        for name in self.col_names[1:]:
            self.y_data[name].append(data[name])

        # Apply rolling buffer
        if not self.keep_all:
            self.x_data = self.x_data[-self.max_points:]
            for name in self.col_names[1:]:
                self.y_data[name] = self.y_data[name][-self.max_points:]

        self._draw_plot()

    def _draw_plot(self):
        for ax, name, color, ylim, ylabel in zip(self.axes, self.col_names[1:], self.colors, self.y_limits, self.y_labels):
            ax.clear()
            ax.plot(self.x_data, self.y_data[name], color=color, label=name)
            #ax.set_ylabel(ylabel, color=color)
            #ax.tick_params(axis='y', colors=color)
            if ylim is not None:
                ax.set_ylim(ylim)
            ax.grid(False)

        #self.ax.set_xlabel(self.col_names[0])
        self.fig.tight_layout()
        #self.ax.legend(loc="upper right", framealpha=0.3) 
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
        if self.col_names[0] not in data or self.col_names[1] not in data:
            return
        
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
        if self.col_names[0] not in data:
            return
            
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
        if self.col_names[0] not in data:
            return
            
        self.set_value(data[self.col_names[0]])

# Predefined flags (works nicely with dropdown menus)
FLAG_STYLES = {
    "Green": {"type": "solid", "color": "green"},
    "Yellow": {"type": "solid", "color": "yellow"},
    "Red": {"type": "solid", "color": "red"},
    "Black": {"type": "solid", "color": "black"},
    "White": {"type": "solid", "color": "white"},
    "Checkered": {"type": "checkered", "colors": ("black", "white")},
}

class FlagWidget(ParentWidget):
    def __init__(self, parent, title="Flag", flag="Green", **kwargs):
        super().__init__(parent, title=title, **kwargs)

        self.aspect_ratio = 3/2  # width:height
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="white")
        self.canvas.pack(expand=True, fill="both")

        self.flag = flag
        self.bind("<Configure>", self._on_resize)
        self.draw_flag()

    def _on_resize(self, event):
        """Adjust height to maintain aspect ratio based on width"""
        new_width = event.width
        new_height = int(new_width / self.aspect_ratio)
        self.canvas.config(width=new_width, height=new_height)
        self.draw_flag()

    def update_data(self, value):
        if isinstance(value, str) and value in FLAG_STYLES:
            self.flag = value
            self.draw_flag()

    def draw_flag(self):
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        style = FLAG_STYLES.get(self.flag, {"type": "solid", "color": "gray"})
        if style["type"] == "solid":
            self.canvas.create_rectangle(0, 0, cw, ch, fill=style["color"], outline="")
        elif style["type"] == "checkered":
            self._draw_checkered(0, 0, cw, ch)

    def _draw_checkered(self, x0, y0, x1, y1):
        rows, cols = 8, 12
        square_w = (x1 - x0) / cols
        square_h = (y1 - y0) / rows
        for row in range(rows):
            for col in range(cols):
                color = "black" if (row + col) % 2 == 0 else "white"
                xs = x0 + col * square_w
                ys = y0 + row * square_h
                xe = xs + square_w
                ye = ys + square_h
                self.canvas.create_rectangle(xs, ys, xe, ye, fill=color, outline="")


class DeviceStatusWidget(ParentWidget):
    STATUS_COLORS = {
        "UP": "green",
        "DEGRADED": "orange",
        "DOWN": "red",
        "UNKNOWN": "gray"
    }

    def __init__(self, parent, **kwargs):
        col_names = ["IP", "Type", "Status"]
        super().__init__(parent, title="Device Status", col_names=col_names, **kwargs)

        self.device_rows = {}  # ip -> row widgets
        self.current_row = 2   # start after headers

    def update_data(self, devices):
        """
        devices: dict[ip] = Device object
        """
        for ip, dev in devices.items():
            status = dev.get_status()
            color = self.STATUS_COLORS.get(status, "gray")

            if ip not in self.device_rows:
                # Create a new row
                ip_label = tk.Label(self, text=ip)
                type_label = tk.Label(self, text=dev.dev_type)
                status_label = tk.Label(self, text=status, fg=color, font=("Arial", 10, "bold"))

                ip_label.grid(row=self.current_row, column=0, padx=5, pady=2)
                type_label.grid(row=self.current_row, column=1, padx=5, pady=2)
                status_label.grid(row=self.current_row, column=2, padx=5, pady=2)

                self.device_rows[ip] = (ip_label, type_label, status_label)
                self.current_row += 1
            else:
                # Update existing row
                _, _, status_label = self.device_rows[ip]
                status_label.config(text=status, fg=color)

class ImageButton(ttk.Button):
    def __init__(self, parent, image_path, text="", command=None, **kwargs):
        super().__init__(parent, command=command, **kwargs)
        self.image_path = image_path
        self.original_img = Image.open(image_path)
        self.display_img = None  # will hold the resized version
        self.text=text

        # Redraw when the widget is resized
        self.bind("<Configure>", self._resize_image)

    def _resize_image(self, event):
        # Button size
        w, h = event.width, event.height
        orig_w, orig_h = self.original_img.size

        # Keep aspect ratio
        scale = min(w / orig_w, h / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)

        # Resize with Pillow
        img_resized = self.original_img.resize((new_w, new_h), Image.LANCZOS)
        self.display_img = ImageTk.PhotoImage(img_resized)

        # Set image on button
        self.config(image=self.display_img, text=self.text, compound="top")
