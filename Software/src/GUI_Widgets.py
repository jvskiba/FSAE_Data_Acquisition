from Device_Manager import *
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
import numpy as np
from matplotlib.patches import Circle
from typing import List
import colorsys

class ParentWidget(tk.Frame):
    def __init__(self, parent, title="Parent", col_names=[], **kwargs):
        super().__init__(parent, **kwargs)
        self.parent = parent
        self.title = title
        self.col_names = col_names
    
    def update_data(self, data):
        """Placeholder method to update widget with data"""
        pass

class InfoBox(ParentWidget):
    def __init__(self, parent, title="", col_name="", precision=2,
                 bg_color="grey", fg_color="white", corner_radius=35, alpha=0.8,
                 padding=5, warn_min=None, warn_max=None, crit_min=None, crit_max=None, age_warn=0.5, age_crit=2.0, **kwargs):
        super().__init__(parent, title=title, col_names=[col_name], **kwargs)

        self.bg_color = bg_color
        self.fg_color = fg_color
        self.corner_radius = corner_radius
        self.alpha = alpha
        self.padding = padding
        self.title = title
        self.precision = precision
        self.init_value = "--"
        self.value = self.init_value
        self.initial_value= self.init_value
        
        # Warning/Critical thresholds
        self.warn_min = warn_min
        self.warn_max = warn_max
        self.crit_min = crit_min
        self.crit_max = crit_max
        self.age_warn = age_warn
        self.age_crit = age_crit
        self.age = None

        # Create canvas
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self.master["bg"])
        self.canvas.pack(fill="both", expand=True)

        self.background_id = None
        self.border_id = None
        self.title_id = None
        self.value_id = None

        # Bind resize to redraw
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        self._draw_background()
        self._draw_text()

    def _get_bg_color(self):
        """Determine background color based on signal value"""

        try:
            val = float(self.value)
        except (ValueError, TypeError):
            return self.bg_color

        if self.crit_min is not None and val < self.crit_min:
            return "red"
        if self.crit_max is not None and val > self.crit_max:
            return "red"

        if self.warn_min is not None and val < self.warn_min:
            return "yellow"
        if self.warn_max is not None and val > self.warn_max:
            return "yellow"

        return self.bg_color
    
    def _get_border_color(self):
        if self.age is None:
            return self.bg_color

        age_sec = max(0.0, self.age)

        # 0s = green (120°)
        # 10s = red (0°)
        t = min(age_sec / 10.0, 1.0)

        # Smooth easing
        t = t * t * (3 - 2 * t)  # smoothstep

        hue = (120 * (1 - t)) / 360.0

        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)

        # Fade brightness after 10s
        if age_sec > 10:
            brightness = max(0.5, 1.0 - (age_sec - 10) / 10)
            r *= brightness
            g *= brightness
            b *= brightness

        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"



    def _draw_background(self):
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)

        border_width = 4
        r = min(self.corner_radius, w//4, h//4)

        fill_color = self._get_bg_color()
        border_color = self._get_border_color()

        alpha_hex = f"{int(self.alpha * 255):02x}"
        fill_color = fill_color + alpha_hex if fill_color.startswith("#") else fill_color

        # Clear old background
        if self.background_id:
            self.canvas.delete(self.background_id)
        if hasattr(self, "border_id") and self.border_id:
            self.canvas.delete(self.border_id)

        # --- Border (outer) ---
        self.border_id = self._create_rounded_rect(
            self.canvas,
            0, 0, w, h,
            r,
            fill=border_color,
            outline=""
        )

        # --- Fill (inner) ---
        self.background_id = self._create_rounded_rect(
            self.canvas,
            border_width,
            border_width,
            w - border_width,
            h - border_width,
            r - border_width,
            fill=fill_color,
            outline=""
        )

    def _update_background(self):
        fill_color = self._get_bg_color()
        border_color = self._get_border_color()

        alpha_hex = f"{int(self.alpha * 255):02x}"
        fill_color = fill_color + alpha_hex if fill_color.startswith("#") else fill_color

        if not self.border_id or not self.background_id:
            self._draw_background()
            return

        self.canvas.itemconfig(self.border_id, fill=border_color)
        self.canvas.itemconfig(self.background_id, fill=fill_color)

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
        
    def _update_text(self):
        if not self.value_id:
            self._draw_text()
            return
        
        self.canvas.itemconfig(self.value_id, text=self.value)

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
        entry = data.get(self.col_names[0])
        if not entry:
            return

        value = entry
        self.age = data.age(self.col_names[0])


        try:
            self.value = f"{value:.{self.precision}f}".rstrip("0").rstrip(".")
        except Exception:
            self.value = str(value)

        self._update_background()
        self._update_text()

class PlotBox(ParentWidget):
    def __init__(self, parent, title="", col_names=None, colors=None,
                 y_limits=None, keep_all=True, max_seconds=500, y_labels=None, compact=False, **kwargs):
        super().__init__(parent, **kwargs)

        if col_names is None:
            return

        self.title = title
        self.col_names = col_names
        self.x_data = []
        self.y_data = {name: [] for name in col_names[1:]}
        self.x_data_disp = []
        self.y_data_disp = {name: [] for name in col_names[1:]}
        self.compact = compact

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
        self.max_seconds = max_seconds
        self.ts_data = []

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

        if not compact:
            self.ax.set_xlabel(col_names[0])
            self.fig.suptitle(title)
            
            # Overlayed legend box (placed relative to canvas)
            self.legend_box = tk.Label(
            self, text="", justify="left",
            font=("TkDefaultFont", 9),
            bg="white", fg="black",
            relief="solid", bd=1
            )
            # Place in top-right corner, adjust relx/rely for positioning
            self.legend_box.place(relx=0.02, rely=0.02, anchor="nw")

        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        # Bind resize
        self.bind("<Configure>", self._on_resize)
        self._draw_plot()

    def _on_resize(self, event):
        dpi = self.fig.get_dpi()
        self.fig.set_size_inches(event.width / dpi, event.height / dpi)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def update_data(self, data):
        now = time.monotonic()

        # --- append timestamp ---
        self.ts_data.append(now)

        # --- append x ---
        if self.col_names[0] == "INDEX":
            self.x_data.append(self.x_data[-1] + 1 if self.x_data else 0)
        elif self.col_names[0] == "TIME":
            #Age based on age of the first data field #TODO: Maybe this is a bad idea
            self.x_data.append(data.timestamp(self.col_names[1]))
        else:
            self.x_data.append(data.get(self.col_names[0], float("nan")))

        # --- append y ---
        for name in self.col_names[1:]:
            self.y_data[name].append(data.get(name, float("nan")))

        # --- rolling buffer (TIME BASED) ---
        if self.keep_all or self.max_seconds == 0:
            self.x_data_disp = list(self.x_data)
            self.y_data_disp = {n: list(v) for n, v in self.y_data.items()}
        else:
            cutoff = now - self.max_seconds

            # find first index >= cutoff
            start = 0
            for i, ts in enumerate(self.ts_data):
                if ts >= cutoff:
                    start = i
                    break
            else:
                start = len(self.ts_data)

            self.x_data_disp = self.x_data[start:]
            self.y_data_disp = {n: v[start:] for n, v in self.y_data.items()}

            # OPTIONAL: prune old data permanently to avoid unbounded growth
            #self.ts_data = self.ts_data[start:]
            #self.x_data = self.x_data[start:]
            #for n in self.y_data:
            #    self.y_data[n] = self.y_data[n][start:]

        self._draw_plot()

    def _draw_plot(self):
        cols = self.col_names[1:]
        n = min(len(self.axes), len(cols), len(self.colors), len(self.y_limits), len(self.y_labels))
        legend_lines = []

        for i in range(n):
            ax = self.axes[i]
            name = cols[i]
            color = self.colors[i]
            ylim = self.y_limits[i]
            ylabel = self.y_labels[i]

            ax.clear()
            x = self.x_data_disp
            y = self.y_data_disp.get(name, [float("nan")] * len(x))

            # Defensive length fix
            if len(x) != len(y):
                min_len = min(len(x), len(y))
                x, y = x[-min_len:], y[-min_len:]


            if ylim is not None:
                ax.set_ylim(ylim)
            ax.set_ylabel("", color=color)
            ax.tick_params(axis="y", which="both", left=False, right=False, labelleft=False, labelright=False)
            if self.compact:
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_xlabel("")
                ax.set_ylabel("")
                ax.grid(False)

                for spine in ax.spines.values():
                    spine.set_visible(False)

                self.line_width = 2.5
            else:
                ax.grid(False)
                self.line_width = 1.2

                # Collect min/max for legend box
                if y:
                    arr = np.array([val for val in y if val is not None and not np.isnan(val)])
                    if arr.size > 0:
                        ymin, ymax = np.min(arr), np.max(arr)
                        legend_lines.append(f"{name} [{ymin:.2f}, {ymax:.2f}]")
            ax.plot(x, y, color=color, label=name)
            
            

        self.fig.tight_layout()
        self.canvas.draw_idle()

        # Update custom legend box
        if legend_lines:
            self.legend_box.config(text="\n".join(legend_lines))

class PlotViewer(ParentWidget):
    def __init__(self, parent, title="", col_names=None, colors=None,
                 y_limits=None, keep_all=True, max_seconds=500, y_labels=None, compact=False, **kwargs):
        super().__init__(parent, **kwargs)

        if col_names is None:
            return
        
        # Left frame: buttons
        self.btn_frame: tk.Frame = tk.Frame(self)
        self.btn_frame.pack(side="left", fill="y", padx=5, pady=5)

        # Right frame: plot
        self.plot_frame: tk.Frame = tk.Frame(self)
        self.plot_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.plot_frame.rowconfigure(0, weight=1)
        self.plot_frame.columnconfigure(0, weight=1)

        # Create PlotBox in right frame
        self.plot = PlotBox(self.plot_frame, title, col_names, colors,
                 y_limits, keep_all, max_seconds, y_labels, compact, **kwargs)
        self.plot.pack(fill="both", expand=True)

        # Track active button
        self.active_btn: tk.StringVar = tk.StringVar(value="All Time")

        # Create buttons
        times: List[tuple[str, int]] = [("All Time", 0), ("5s", 5), ("10s", 10), ("30s", 30), ("60s", 60)]
        for label, secs in times:
            btn: tk.Button = tk.Button(self.btn_frame, text=label, command=lambda l=label, s=secs: self.set_plot_window(l, s))
            btn.pack(fill="x", pady=2)

        # Initialize highlight
        self.set_plot_window("All Time", 0)

    def _on_resize(self, event):
        self.plot._on_resize(event)

    def update_data(self, data):
        self.plot.update_data(data)
    
    # Button callback
    def set_plot_window(self, label: str, seconds: int):
        # Update plot rolling window
        if seconds == 0:
            self.plot.keep_all = True
        else:
            self.plot.keep_all = False
            self.plot.max_seconds = seconds

        # Update button highlights
        self.active_btn.set(label)
        for child in self.btn_frame.winfo_children():
            if isinstance(child, tk.Button):  # type guard for Pylance
                if child["text"] == label:
                    child.config(bg="lightblue")
                else:
                    child.config(bg="SystemButtonFace")

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
            circle = Circle((0, 0), radius, color="gray", fill=False, ls="--", lw=0.7)
            self.ax.add_artist(circle)

        self.ax.set_xlabel("Lateral G")
        self.ax.set_ylabel("Longitudinal G")      

    def _on_resize(self, event):
        size = min(self.winfo_width(), self.winfo_height())
        self.config(width=size, height=size)

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
    def __init__(self, parent, title="", col_name=None, max_value=100, bar_color="green", **kwargs):
        super().__init__(parent, title=title, col_names=[col_name], **kwargs)

        self.max_value = max_value
        self.bar_color = bar_color
        self.col_name = col_name
        self.current_value = 0

        # Title at the top
        self.title_label = tk.Label(self, text=title, font=("Arial", 10, "bold"))
        self.title_label.pack(pady=(0, 2))

        # Canvas expands with frame
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=1, highlightbackground="black")
        self.canvas.pack(fill="both", expand=True)

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
        entry = data.get(self.col_name)
        if not entry:
            return
        self.current_value = entry
        self._draw_bar()

class HorizontalIndicator(ParentWidget):
    def __init__(self, parent, title="STR", col_name=None, min_value=-540, max_value=540,
                 bar_color="lightgray", line_color="blue", midline_color="black", **kwargs):
        super().__init__(parent, title=title, col_names=[col_name], **kwargs)

        self.min_value = min_value
        self.max_value = max_value
        self.line_color = line_color
        self.midline_color = midline_color

        # Title and value labels
        self.title_label = tk.Label(self, text=title, font=("Arial", 10, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

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