from Telem import *
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from PIL import Image, ImageTk

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



import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
import numpy as np

class PlotBox(tk.Frame):  # I swapped ParentWidget→tk.Frame for demo; swap back in your code
    def __init__(self, parent, title="", col_names=None, colors=None,
                 y_limits=None, keep_all=True, max_points=500, y_labels=None, **kwargs):
        super().__init__(parent, **kwargs)

        if col_names is None:
            return

        self.title = title
        self.col_names = col_names
        self.x_data = []
        self.y_data = {name: [] for name in col_names[1:]}
        self.x_data_disp = []
        self.y_data_disp = {name: [] for name in col_names[1:]}

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

        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        # Overlayed legend box (placed relative to canvas)
        self.legend_box = tk.Label(
            self, text="", justify="left",
            font=("TkDefaultFont", 9),
            bg="white", fg="black",
            relief="solid", bd=1
        )
        # Place in top-right corner, adjust relx/rely for positioning
        self.legend_box.place(relx=0.02, rely=0.02, anchor="nw")

        # Bind resize
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        dpi = self.fig.get_dpi()
        self.fig.set_size_inches(event.width / dpi, event.height / dpi)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def update_data(self, data):
        # --- append x ---
        if self.col_names[0] == "INDEX":
            self.x_data.append(self.x_data[-1] + 1 if self.x_data else 0)
        else:
            self.x_data.append(data.get(self.col_names[0]))

        # --- append y ---
        for name in self.col_names[1:]:
            self.y_data[name].append(data.get(name, float("nan")))

        # --- rolling buffer ---
        if self.keep_all:
            self.x_data_disp = list(self.x_data)
            self.y_data_disp = {n: list(v) for n, v in self.y_data.items()}
        else:
            max_pts = max(1, self.max_points)
            start = max(0, len(self.x_data) - max_pts)
            self.x_data_disp = list(self.x_data[start:])
            self.y_data_disp = {n: list(v[start:]) for n, v in self.y_data.items()}

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

            ax.plot(x, y, color=color, label=name)
            if ylim is not None:
                ax.set_ylim(ylim)
            ax.set_ylabel("", color=color)
            ax.tick_params(axis="y", which="both", left=False, right=False, labelleft=False, labelright=False)
            ax.grid(False)

            # Collect min/max for legend box
            if y:
                arr = np.array([val for val in y if val is not None and not np.isnan(val)])
                if arr.size > 0:
                    ymin, ymax = np.min(arr), np.max(arr)
                    legend_lines.append(f"{name} [{ymin:.2f}, {ymax:.2f}]")

        self.fig.tight_layout()
        self.canvas.draw_idle()

        # Update custom legend box
        if legend_lines:
            self.legend_box.config(text="\n".join(legend_lines))
        else:
            self.legend_box.config(text="")


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

import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt


# -------------------------
# Reusable table widget
# -------------------------
class TimingTable(ttk.Frame):
    def __init__(self, parent, sectors, **kwargs):
        super().__init__(parent, **kwargs)

        self.sector_names = [f"{s.start_gate}->{s.end_gate}" for s in sectors]
        columns = ["Lap"] + self.sector_names

        # Treeview
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="extended",  # Ctrl + Shift selection
        )
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=100, stretch=True)

        self.tree.grid(row=0, column=0, sticky="nsew")

        # Scrollbars
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Resizing
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Copy shortcut
        self.tree.bind("<Control-c>", self.copy_selection)
        self.tree.bind("<Control-C>", self.copy_selection)

    def update_table(self, laps):
        """Refresh table with list of Lap objects."""
        self.tree.delete(*self.tree.get_children())
        for lap in laps:
            row = [lap.lap_number]
            for name in self.sector_names:
                val = lap.sector_times.get(name)
                row.append(round(val, 3) if val is not None else "---")
            self.tree.insert("", "end", values=row)

    def copy_selection(self, event=None):
        """Copy selected rows to clipboard (tab-separated)."""
        items = self.tree.selection()
        rows = []
        for item in items:
            values = self.tree.item(item, "values")
            rows.append("\t".join(str(v) for v in values))
        text = "\n".join(rows)

        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()  # ensures persistence

        return "break"  # prevent bell sound


# -------------------------
# Full Timing GUI
# -------------------------
class TimingGUI:
    def __init__(self, root, timing_controller):
        self.root = root
        self.tc = timing_controller

        # Layout
        root.rowconfigure(0, weight=2)   # table
        root.rowconfigure(1, weight=0)   # toggles
        root.rowconfigure(2, weight=3)   # plot
        root.columnconfigure(0, weight=1)

        # Table
        self.table = TimingTable(root, self.tc.sectors)
        self.table.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # Sector toggles
        self.toggle_frame = ttk.Frame(root)
        self.toggle_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.sector_vars = {}
        sector_names = [f"{s.start_gate}->{s.end_gate}" for s in self.tc.sectors]
        for name in sector_names:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(
                self.toggle_frame,
                text=name,
                variable=var,
                command=self.update_ui
            )
            cb.pack(side="left", padx=5)
            self.sector_vars[name] = var

        # Plot
        self.fig, self.ax = plt.subplots(figsize=(6, 3))
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().grid(row=2, column=0, columnspan=2, sticky="nsew")

        # Initial draw
        self.update_ui()

    def update_ui(self):
        """Refresh table and plot."""
        laps = self.tc.get_lap_times()
        self.table.update_table(laps)

        # Plot
        self.ax.clear()
        selected = [s for s, var in self.sector_vars.items() if var.get()]

        if not selected:  # Default to lap totals
            lap_numbers, lap_totals = [], []
            for lap in self.tc.laps:
                times = [t for t in lap.sector_times.values() if t is not None]
                if times:
                    lap_numbers.append(lap.lap_number)
                    lap_totals.append(sum(times))
            if lap_numbers:
                self.ax.plot(lap_numbers, lap_totals, marker="o", label="Total Lap")
        else:
            for sector_name in selected:
                lap_numbers, sector_times = [], []
                for lap in self.tc.laps:
                    t = lap.sector_times.get(sector_name)
                    if t is not None:
                        lap_numbers.append(lap.lap_number)
                        sector_times.append(t)
                if lap_numbers:
                    self.ax.plot(
                        lap_numbers, sector_times, marker="o", label=sector_name
                    )

        self.ax.set_xlabel("Lap")
        self.ax.set_ylabel("Time (s)")
        self.ax.set_title("Timing Trends")
        self.ax.grid(True)
        self.ax.legend()
        self.canvas.draw()



class TimingTable(ttk.Frame):
    def __init__(self, parent, sectors, **kwargs):
        super().__init__(parent, **kwargs)

        self.sector_names = [f"{s.start_gate}->{s.end_gate}" for s in sectors]
        columns = ["Lap"] + self.sector_names

        # -------------------------
        # Treeview
        # -------------------------
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="extended",  # allows Ctrl + Shift multi-select
        )
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=100, stretch=True)

        self.tree.grid(row=0, column=0, sticky="nsew")

        # Scrollbars
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Configure frame resizing
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # -------------------------
        # Key bindings
        # -------------------------
        self.tree.bind("<Control-c>", self.copy_selection)
        self.tree.bind("<Control-C>", self.copy_selection)  # uppercase too

    # -------------------------
    # Public methods
    # -------------------------
    def update_table(self, laps):
        """Refresh table with list of Lap objects."""
        self.tree.delete(*self.tree.get_children())
        for lap in laps:
            row = [lap.lap_number]
            for name in self.sector_names:
                val = lap.sector_times.get(name)
                row.append(round(val, 3) if val is not None else "---")
            self.tree.insert("", "end", values=row)

    def copy_selection(self, event=None):
        """Copy selected rows to clipboard (tab-separated)."""
        items = self.tree.selection()
        rows = []
        for item in items:
            values = self.tree.item(item, "values")
            rows.append("\t".join(str(v) for v in values))
        text = "\n".join(rows)

        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()  # ensures persistence

        return "break"  # prevent default bell sound
