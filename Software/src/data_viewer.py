import os
import sys
import random
import pickle
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QMessageBox, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QFileDialog, QTextEdit, QDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QFont

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.figure import Figure


# Class storing graph visual settings
class GraphStyle:
    def __init__(self, show_min=False, show_max=False, show_stddev=False, show_grid_lines=True,
                 enforce_square=False, custom_plot_title="", connect_points=False,
                 enforce_color_range=False, trend_line_type="None", trend_line_color="black",
                 polynomial_order=2, moving_average_length=10, marker_size=10,
                 marker_color="blue", marker_style="o", line_name=""):
        self.show_min = show_min
        self.show_max = show_max
        self.show_stddev = show_stddev
        self.show_grid_lines = show_grid_lines
        self.enforce_square = enforce_square
        self.custom_plot_title = custom_plot_title
        self.connect_points = connect_points
        self.enforce_color_range = enforce_color_range
        self.trend_line_type = trend_line_type
        self.trend_line_color = trend_line_color
        self.polynomial_order = polynomial_order
        self.moving_average_length = moving_average_length
        self.marker_size = marker_size
        self.marker_color = marker_color
        self.marker_style = marker_style
        self.line_name = line_name


# Container for plot data and settings
class GraphObject:
    def __init__(self, plot_type, graph_style: GraphStyle, x_data, y_data, z_data, names, plot_title):
        self.plot_type = plot_type  # 0: 2D, 1: 3D Color, 2: 3D Scatter
        self.graph_style = graph_style
        self.x_data = x_data
        self.y_data = y_data
        self.z_data = z_data
        self.names = names  # [x_name, y_name, z_name]
        self.plot_title = plot_title


def movingaverage(interval, window_size):
    window = np.ones(int(window_size)) / float(window_size)
    return np.convolve(interval, window, 'same')


def logarithm(x, a, b):
    return a * np.log(x) + b


# Plotting Functions
def make_plot_2D(figure, graph_object: GraphObject):
    x_vals = np.array(graph_object.x_data, dtype=float)
    y_vals = np.array(graph_object.y_data, dtype=float)

    plot = figure.add_subplot(111)

    if graph_object.graph_style.connect_points:
        plot.plot(x_vals, y_vals, color=graph_object.graph_style.marker_color, linewidth=0.5)

    plot.scatter(
        x_vals, y_vals,
        marker=graph_object.graph_style.marker_style,
        label=graph_object.graph_style.line_name if graph_object.graph_style.line_name else None,
        s=graph_object.graph_style.marker_size,
        c=graph_object.graph_style.marker_color
    )

    if graph_object.graph_style.trend_line_type == "Linear":
        coefficients = np.polyfit(x_vals, y_vals, 1)
        trendline = np.poly1d(coefficients)
        plot.plot(x_vals, trendline(x_vals), color=graph_object.graph_style.trend_line_color)

    elif graph_object.graph_style.trend_line_type == "Polynomial":
        coefficients = np.polyfit(x_vals, y_vals, graph_object.graph_style.polynomial_order)
        poly_function = np.poly1d(coefficients)
        plot.plot(x_vals, poly_function(x_vals), color=graph_object.graph_style.trend_line_color)

    elif graph_object.graph_style.trend_line_type == "Moving Average":
        y_avgs = movingaverage(y_vals, graph_object.graph_style.moving_average_length)
        plot.plot(x_vals, y_avgs, color=graph_object.graph_style.trend_line_color)

    elif graph_object.graph_style.trend_line_type == "Logarithmic":
        try:
            params, _ = curve_fit(logarithm, x_vals, y_vals)
            plot.plot(x_vals, logarithm(x_vals, *params), color=graph_object.graph_style.trend_line_color)
        except Exception:
            pass

    if graph_object.graph_style.line_name:
        plot.legend()

    plot.set_xlabel(graph_object.names[0])
    plot.set_ylabel(graph_object.names[1])
    plot.set_title(graph_object.plot_title)
    plot.grid(graph_object.graph_style.show_grid_lines)

    plot_annotation = ""
    if graph_object.graph_style.show_min:
        plot_annotation += f"X Min: {np.min(x_vals):.2f} Y Min: {np.min(y_vals):.2f}"
    if graph_object.graph_style.show_max:
        plot_annotation += f"\nX Max: {np.max(x_vals):.2f} Y Max: {np.max(y_vals):.2f}"
    if graph_object.graph_style.show_stddev:
        plot_annotation += f"\nX StdDev: {np.std(x_vals):.2f} Y StdDev: {np.std(y_vals):.2f}"

    if plot_annotation.strip():
        annotation = plot.annotate(text=plot_annotation, xy=(x_vals[0], y_vals[0]), bbox=dict(facecolor="white"))
        annotation.draggable()

    if graph_object.graph_style.enforce_square:
        max_range = max(np.max(x_vals) - np.min(x_vals), np.max(y_vals) - np.min(y_vals)) / 1.8
        center_x = (np.max(x_vals) + np.min(x_vals)) / 2.0
        center_y = (np.max(y_vals) + np.min(y_vals)) / 2.0
        plot.set_xlim(center_x - max_range, center_x + max_range)
        plot.set_ylim(center_y - max_range, center_y + max_range)
        plot.set_box_aspect(1)


def make_plot_3D_color(figure, graph_object: GraphObject):
    x_vals = np.array(graph_object.x_data, dtype=float)
    y_vals = np.array(graph_object.y_data, dtype=float)
    color_vals = np.array(graph_object.z_data, dtype=float)

    plot = figure.add_subplot(111)

    scatter = plot.scatter(
        x_vals, y_vals, c=color_vals, cmap='nipy_spectral',
        marker=graph_object.graph_style.marker_style,
        label=graph_object.graph_style.line_name if graph_object.graph_style.line_name else None,
        s=graph_object.graph_style.marker_size
    )

    if graph_object.graph_style.connect_points:
        plot.plot(x_vals, y_vals, color="black", linewidth=0.5)

    cbar = figure.colorbar(scatter, ax=plot)
    cbar.set_label(graph_object.names[2])

    plot.set_title(graph_object.plot_title)
    plot.set_xlabel(graph_object.names[0])
    plot.set_ylabel(graph_object.names[1])
    plot.grid(graph_object.graph_style.show_grid_lines)


def make_plot_3D(figure, graph_object: GraphObject):
    x_vals = np.array(graph_object.x_data, dtype=float)
    y_vals = np.array(graph_object.y_data, dtype=float)
    z_vals = np.array(graph_object.z_data, dtype=float)

    plot = figure.add_subplot(111, projection='3d')
    plot.set_title(graph_object.plot_title)
    plot.set_xlabel(graph_object.names[0])
    plot.set_ylabel(graph_object.names[1])
    plot.set_zlabel(graph_object.names[2])

    plot.scatter(
        x_vals, y_vals, z_vals, alpha=0.8,
        marker=graph_object.graph_style.marker_style,
        label=graph_object.graph_style.line_name if graph_object.graph_style.line_name else None,
        s=graph_object.graph_style.marker_size,
        c=graph_object.graph_style.marker_color
    )

    if graph_object.graph_style.connect_points:
        plot.plot(x_vals, y_vals, z_vals, color=graph_object.graph_style.marker_color)

    plot.grid(graph_object.graph_style.show_grid_lines)


# Matplotlib Canvas Component
class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(fig)


# Main Application Window
class DataVisualizationTool(QMainWindow):
    UGA_RED = "#BA0C2F"  # Theme color

    def __init__(self, root_dir):
        super().__init__()

        self.data_df = None
        self.graph_style = GraphStyle()

        self.root_dir = root_dir
        self.presets_file = root_dir + "/PRESETS.csv"

        self.setWindowTitle("Data Visualization Tool")
        self.setMinimumWidth(1080)
        self.setMinimumHeight(720)

        central_widget = QWidget()
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)

        # Title Section (UGA Red Theme)
        self.title_label = QLabel("Data Visualization Tool")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFixedHeight(80)
        self.title_label.setFont(QFont("Arial", 36, QFont.Weight.Bold))
        self.set_title_theme()
        main_layout.addWidget(self.title_label)

        # File Path Input Section
        file_path_layout = QHBoxLayout()
        file_path_label = QLabel("File Path:")
        self.file_path_input = QLineEdit()
        browse_file_button = QPushButton("Browse CSV")
        browse_file_button.clicked.connect(self.browse_file)

        file_path_layout.addWidget(file_path_label)
        file_path_layout.addWidget(self.file_path_input)
        file_path_layout.addWidget(browse_file_button)
        main_layout.addLayout(file_path_layout)

        # Axis Selection Section
        self.axis_section_layout = QHBoxLayout()

        self.x_dropdown = QComboBox()
        self.y_dropdown = QComboBox()
        self.z_dropdown = QComboBox()

        self.axis_section_layout.addLayout(self.create_axis_layout("X-Axis", self.x_dropdown))
        self.axis_section_layout.addLayout(self.create_axis_layout("Y-Axis", self.y_dropdown))
        self.axis_section_layout.addLayout(self.create_axis_layout("Z-Axis", self.z_dropdown))

        main_layout.addLayout(self.axis_section_layout)

        # Extra Options Section
        self.extra_options_layout = QHBoxLayout()
        self.use_z_axis_checkbox = QCheckBox("Use Z-Axis")
        self.use_z_axis_checkbox.stateChanged.connect(self.toggle_z_axis)
        self.apply_z_as_color_checkbox = QCheckBox("Apply Z-Axis as Color")
        self.extra_options_layout.addWidget(self.use_z_axis_checkbox)
        self.extra_options_layout.addWidget(self.apply_z_as_color_checkbox)

        self.preset_graphing_dropdown = QComboBox()
        self.preset_graphs = self.get_preset_graphs()
        self.preset_graphing_dropdown.addItems(self.preset_graphs)
        self.preset_graphing_dropdown.currentIndexChanged.connect(self.execute_preset_graph)
        self.extra_options_layout.addWidget(self.preset_graphing_dropdown)

        main_layout.addLayout(self.extra_options_layout)

        # Graph Buttons Section
        self.graph_buttons_layout = QHBoxLayout()
        self.generate_graph_button = QPushButton("Generate Graph")
        self.generate_graph_button.clicked.connect(lambda: self.generate_graph(False))
        self.IFL_Button = QPushButton("I'm Feelin Lucky")
        self.IFL_Button.clicked.connect(self.random_graph)

        self.extra_graph_buttons_dropdown = QComboBox()
        self.extra_graph_options = {
            "Extra Graphing Options:": lambda: None,
            "Create Pop Out Graph": self.full_screen_figure,
            "Save Graph": self.save_graph,
            "Open Saved Graph": self.open_saved_graph,
            "Save Preset Graph": self.save_preset_graph,
            "Remove Preset Graph": self.remove_preset_graph,
            "Modify Graph Style": self.modify_graph_style,
            "Clear Graph": self.clear_graph
        }
        self.extra_graph_buttons_dropdown.addItems(self.extra_graph_options.keys())
        self.extra_graph_buttons_dropdown.currentIndexChanged.connect(self.execute_extra_graph_button)

        self.zen_mode_button = QPushButton("Toggle Zen Mode")
        self.zen_mode_button.clicked.connect(self.enter_zen_mode)
        self.zen = False

        self.graph_buttons_layout.addWidget(self.generate_graph_button)
        self.graph_buttons_layout.addWidget(self.IFL_Button)
        self.graph_buttons_layout.addWidget(self.zen_mode_button)
        self.graph_buttons_layout.addWidget(self.extra_graph_buttons_dropdown)
        main_layout.addLayout(self.graph_buttons_layout)

        # Canvas Section for Plots
        canvas_layout = QVBoxLayout()
        self.canvas = MplCanvas(width=5, height=4, dpi=120)
        self.array_window = []
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        canvas_layout.addWidget(self.toolbar)
        canvas_layout.addWidget(self.canvas)
        main_layout.addLayout(canvas_layout)

        # Terminal Section
        self.terminal_title = QLabel("Terminal:")
        self.terminal_title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.terminal_title.setStyleSheet(f"color: {self.UGA_RED};")
        main_layout.addWidget(self.terminal_title)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet("background-color: #1E1E1E; color: white; font-family: Consolas;")
        self.terminal.setFixedHeight(80)
        main_layout.addWidget(self.terminal)

        self.set_elements_enabled(False)

    def set_title_theme(self):
        palette = self.title_label.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.UGA_RED))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("white"))
        self.title_label.setAutoFillBackground(True)
        self.title_label.setPalette(palette)

    def create_axis_layout(self, axis_name, dropdown):
        layout = QVBoxLayout()
        label = QLabel(axis_name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {self.UGA_RED};")
        layout.addWidget(label)
        layout.addWidget(dropdown)
        return layout

    def set_elements_enabled(self, enabled):
        self.axis_section_layout.setEnabled(enabled)
        self.extra_options_layout.setEnabled(enabled)
        self.graph_buttons_layout.setEnabled(enabled)
        self.toggle_z_axis(False)

    def toggle_z_axis(self, enabled):
        self.z_dropdown.setEnabled(enabled)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self.file_path_input.setText(file_path)
            self.log_message(f"Selected file: {file_path}")
            self.load_data()

    def load_data(self):
        file_path = self.file_path_input.text()
        if os.path.isfile(file_path):
            try:
                self.data_df = pd.read_csv(file_path)
                headers = list(self.data_df.columns)

                for dropdown in [self.x_dropdown, self.y_dropdown, self.z_dropdown]:
                    dropdown.clear()
                    dropdown.addItems(headers)

                self.set_elements_enabled(True)
                self.log_message("CSV file successfully loaded!")
            except Exception as e:
                self.log_message(f"Failed to read CSV: {e}")
        else:
            self.log_message("Invalid file path specified.")

    def log_message(self, message: str):
        self.terminal.append(message)

    def generate_graph(self, return_params=False):
        if self.data_df is None:
            return

        x_col = self.x_dropdown.currentText()
        y_col = self.y_dropdown.currentText()
        z_col = self.z_dropdown.currentText()

        z_enabled = self.use_z_axis_checkbox.isChecked()
        z_color = self.apply_z_as_color_checkbox.isChecked()

        plot_title = self.graph_style.custom_plot_title or (
            f"{y_col} vs. {x_col} vs. {z_col}" if z_enabled else f"{y_col} vs. {x_col}"
        )

        plot_type = 0 if not z_enabled else (1 if z_color else 2)

        # Drop NaNs for graphing columns
        selected_cols = [x_col, y_col] + ([z_col] if z_enabled else [])
        clean_df = self.data_df[selected_cols].dropna()

        x_data = clean_df[x_col].values
        y_data = clean_df[y_col].values
        z_data = clean_df[z_col].values if z_enabled else []

        graph_obj = GraphObject(plot_type, self.graph_style, x_data, y_data, z_data, [x_col, y_col, z_col], plot_title)

        if return_params:
            return graph_obj

        self.canvas.figure.clear()
        figure = self.canvas.figure

        if plot_type == 0:
            make_plot_2D(figure, graph_obj)
        elif plot_type == 1:
            make_plot_3D_color(figure, graph_obj)
        else:
            make_plot_3D(figure, graph_obj)

        self.canvas.draw()

    def full_screen_figure(self):
        w = BreakoutWindow()
        graph_obj = self.generate_graph(True)
        w.fullscreen_graph(graph_obj)
        w.showMaximized()
        self.array_window.append(w)

    def save_graph(self):
        try:
            graph_obj = self.generate_graph(True)
            name, _ = QFileDialog.getSaveFileName(self, "Save Graph Object", "./", "Graph Object (*.MRGO)")
            if name:
                with open(name, 'wb') as file:
                    pickle.dump(graph_obj, file)
                self.log_message("Graph saved successfully!")
        except Exception as e:
            self.log_message(f"Error saving graph: {e}")

    def open_saved_graph(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Select Saved Graph", "./", "Graph Object (*.MRGO)")
            if path:
                with open(path, 'rb') as file:
                    pickled_object = pickle.load(file)
                w = BreakoutWindow()
                w.fullscreen_graph(pickled_object)
                w.showMaximized()
                self.array_window.append(w)
        except Exception as e:
            self.log_message(f"Error opening graph: {e}")

    def clear_graph(self):
        self.canvas.figure.clear()
        self.canvas.draw()

    def execute_extra_graph_button(self):
        self.extra_graph_options[self.extra_graph_buttons_dropdown.currentText()]()
        self.extra_graph_buttons_dropdown.setCurrentIndex(0)

    def get_preset_graphs(self):
        ret_list = ["Load Preset Graph"]
        if os.path.exists(self.presets_file):
            with open(self.presets_file, "r") as f:
                f.readline()
                for line in f:
                    if line.strip():
                        ret_list.append(line.split(",")[0])
        return ret_list

    def execute_preset_graph(self):
        selection = self.preset_graphing_dropdown.currentText()
        if selection == "Load Preset Graph":
            return
        if os.path.exists(self.presets_file):
            with open(self.presets_file, "r") as f:
                f.readline()
                for line in f:
                    parts = line.strip().split(",")
                    if parts[0] == selection:
                        self.x_dropdown.setCurrentText(parts[1])
                        self.y_dropdown.setCurrentText(parts[2])
                        self.z_dropdown.setCurrentText(parts[3])
                        self.use_z_axis_checkbox.setChecked(parts[4] == "True")
                        self.apply_z_as_color_checkbox.setChecked(parts[5] == "True")
                        self.generate_graph(False)
                        break
        self.preset_graphing_dropdown.setCurrentIndex(0)

    def save_preset_graph(self):
        save_preset_dialog = SavePresetPopoutWindow(self)
        if save_preset_dialog.exec() == QDialog.DialogCode.Accepted:
            preset_name = save_preset_dialog.get_name()
            if not os.path.exists(self.presets_file):
                with open(self.presets_file, "w") as f:
                    f.write("name,x_sel,y_sel,z_sel,use_z,z_as_color\n")
            with open(self.presets_file, "a") as f:
                line = f"{preset_name},{self.x_dropdown.currentText()},{self.y_dropdown.currentText()},{self.z_dropdown.currentText()},{self.use_z_axis_checkbox.isChecked()},{self.apply_z_as_color_checkbox.isChecked()}\n"
                f.write(line)
            self.preset_graphs = self.get_preset_graphs()
            self.preset_graphing_dropdown.clear()
            self.preset_graphing_dropdown.addItems(self.preset_graphs)

    def remove_preset_graph(self):
        remove_dialog = RemovePresetPopoutWindow(self.preset_graphs, self)
        if remove_dialog.exec() == QDialog.DialogCode.Accepted:
            preset_name = remove_dialog.get_name()
            if os.path.exists(self.presets_file):
                lines = []
                with open(self.presets_file, "r") as f:
                    lines = f.readlines()
                with open(self.presets_file, "w") as f:
                    for line in lines:
                        if line.split(",")[0] != preset_name:
                            f.write(line)
            self.preset_graphs = self.get_preset_graphs()
            self.preset_graphing_dropdown.clear()
            self.preset_graphing_dropdown.addItems(self.preset_graphs)

    def modify_graph_style(self):
        dialog = ModifyGraphStyle(self.graph_style, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.graph_style = dialog.get_graph_style()

    def enter_zen_mode(self):
        self.zen = not self.zen
        self.terminal_title.setVisible(not self.zen)
        self.terminal.setVisible(not self.zen)
        self.extra_graph_buttons_dropdown.setVisible(not self.zen)

    def random_graph(self):
        if self.x_dropdown.count() > 0:
            self.x_dropdown.setCurrentIndex(random.randint(0, self.x_dropdown.count() - 1))
            self.y_dropdown.setCurrentIndex(random.randint(0, self.y_dropdown.count() - 1))
            self.z_dropdown.setCurrentIndex(random.randint(0, self.z_dropdown.count() - 1))
            self.use_z_axis_checkbox.setChecked(True)
            self.apply_z_as_color_checkbox.setChecked(True)
            self.generate_graph(False)


# Breakout Fullscreen Graph Window
class BreakoutWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        central_widget = QWidget()
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.canvas = MplCanvas(width=5, height=4, dpi=150)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def fullscreen_graph(self, graph_object):
        self.canvas.figure.clear()
        figure = self.canvas.figure
        if graph_object.plot_type == 0:
            make_plot_2D(figure, graph_object)
        elif graph_object.plot_type == 1:
            make_plot_3D_color(figure, graph_object)
        else:
            make_plot_3D(figure, graph_object)
        self.canvas.draw()


# Save Preset Dialog
class SavePresetPopoutWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Preset")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Enter Preset Name:"))
        self.preset_name_input = QLineEdit()
        layout.addWidget(self.preset_name_input)
        confirm_button = QPushButton("Save")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)
        self.setLayout(layout)

    def get_name(self):
        return self.preset_name_input.text()


# Remove Preset Dialog
class RemovePresetPopoutWindow(QDialog):
    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remove Preset")
        layout = QVBoxLayout()
        self.dropdown = QComboBox()
        self.dropdown.addItems(names)
        layout.addWidget(self.dropdown)
        confirm_button = QPushButton("Remove")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)
        self.setLayout(layout)

    def get_name(self):
        return self.dropdown.currentText()


# Graph Style Configuration Window
class ModifyGraphStyle(QDialog):
    def __init__(self, graph_style: GraphStyle, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modify Graph Style")
        self.layout = QVBoxLayout()

        self.show_min_checkbox = QCheckBox("Show Min")
        self.show_min_checkbox.setChecked(graph_style.show_min)
        self.show_max_checkbox = QCheckBox("Show Max")
        self.show_max_checkbox.setChecked(graph_style.show_max)
        self.show_stddev_checkbox = QCheckBox("Show Standard Deviation")
        self.show_stddev_checkbox.setChecked(graph_style.show_stddev)
        self.show_grid_lines_checkbox = QCheckBox("Enable Grid Lines")
        self.show_grid_lines_checkbox.setChecked(graph_style.show_grid_lines)
        self.enforce_square_graph_checkbox = QCheckBox("Enforce Square Aspect Ratio")
        self.enforce_square_graph_checkbox.setChecked(graph_style.enforce_square)
        self.connect_points_checkbox = QCheckBox("Connect Points with Line")
        self.connect_points_checkbox.setChecked(graph_style.connect_points)

        self.custom_plot_title_input = QLineEdit(graph_style.custom_plot_title)

        self.trend_line_dropdown = QComboBox()
        self.trend_line_dropdown.addItems(["None", "Linear", "Polynomial", "Moving Average", "Logarithmic"])
        self.trend_line_dropdown.setCurrentText(graph_style.trend_line_type)

        self.trend_line_color_dropdown = QComboBox()
        self.trend_line_color_dropdown.addItems(["black", "grey", "red", "green", "blue"])
        self.trend_line_color_dropdown.setCurrentText(graph_style.trend_line_color)

        self.marker_size_input = QLineEdit(str(graph_style.marker_size))
        self.marker_color_dropdown = QComboBox()
        self.marker_color_dropdown.addItems(["black", "grey", "red", "green", "blue"])
        self.marker_color_dropdown.setCurrentText(graph_style.marker_color)

        self.layout.addWidget(self.show_min_checkbox)
        self.layout.addWidget(self.show_max_checkbox)
        self.layout.addWidget(self.show_stddev_checkbox)
        self.layout.addWidget(self.show_grid_lines_checkbox)
        self.layout.addWidget(self.enforce_square_graph_checkbox)
        self.layout.addWidget(self.connect_points_checkbox)

        self.layout.addWidget(QLabel("Custom Title:"))
        self.layout.addWidget(self.custom_plot_title_input)
        self.layout.addWidget(QLabel("Trendline Type:"))
        self.layout.addWidget(self.trend_line_dropdown)
        self.layout.addWidget(QLabel("Trendline Color:"))
        self.layout.addWidget(self.trend_line_color_dropdown)
        self.layout.addWidget(QLabel("Marker Size:"))
        self.layout.addWidget(self.marker_size_input)
        self.layout.addWidget(QLabel("Marker Color:"))
        self.layout.addWidget(self.marker_color_dropdown)

        confirm_btn = QPushButton("Save Settings")
        confirm_btn.clicked.connect(self.accept)
        self.layout.addWidget(confirm_btn)
        self.setLayout(self.layout)

    def get_graph_style(self):
        return GraphStyle(
            show_min=self.show_min_checkbox.isChecked(),
            show_max=self.show_max_checkbox.isChecked(),
            show_stddev=self.show_stddev_checkbox.isChecked(),
            show_grid_lines=self.show_grid_lines_checkbox.isChecked(),
            enforce_square=self.enforce_square_graph_checkbox.isChecked(),
            custom_plot_title=self.custom_plot_title_input.text(),
            connect_points=self.connect_points_checkbox.isChecked(),
            trend_line_type=self.trend_line_dropdown.currentText(),
            trend_line_color=self.trend_line_color_dropdown.currentText(),
            marker_size=float(self.marker_size_input.text() or 5),
            marker_color=self.marker_color_dropdown.currentText()
        )

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller executable
        root_dir = os.path.dirname(sys.executable) + "\\"
    else:
        # Running normally from Python/IDE
        root_dir = os.path.dirname(os.path.abspath(__file__)) + "\\"

    os.environ["QT_API"] = "PyQt6"
    app = QApplication(sys.argv)
    window = DataVisualizationTool(root_dir)
    window.showMaximized()
    app.exec()