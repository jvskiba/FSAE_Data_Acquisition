import json
import os
from GUI_Widgets import *

'''
Layout
Root -> grid
    Frames -> grid
        Widget Frame -> Packing
            Widget Elements
'''

widget_registry = {
    "InfoBox": InfoBox,
    "PlotBox": PlotBox,
    "PlotViewer": PlotViewer,
    "GCirclePlot": GCirclePlot,
    "VerticalBar": VerticalBar,
    "HorizontalIndicator": HorizontalIndicator
}

class LayoutManager:
    def __init__(self, parent, widget_registry):
        self.parent = parent
        self.registry = widget_registry

        self.widgets = []
        self.widget_map = {}

    def load_layout(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Layout file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        self._build_from_layout(data)

    def _build_from_layout(self, data):
        for frame_def in data.get("frames", []):
            frame = self._create_frame(self.parent, frame_def)

            for widget_def in frame_def.get("widgets", []):
                self._create_widget(frame, widget_def)

    def _create_frame(self, parent, frame_def):
        layout = frame_def.get("layout", {})

        row = layout.get("row", 0)
        column = layout.get("column", 0)
        rowspan = layout.get("rowspan", 1)
        columnspan = layout.get("columnspan", 1)

        padx = layout.get("padx", 5)
        pady = layout.get("pady", 5)

        sticky = layout.get("sticky", "nsew")

        #
        # Make grid cells expandable
        #
        for r in range(row, row + rowspan):
            parent.grid_rowconfigure(r, weight=1)

        for c in range(column, column + columnspan):
            parent.grid_columnconfigure(c, weight=1)

        #
        # Create widget
        #
        frame = tk.Frame(parent )
        frame.grid_propagate(False)  # Prevents shrinking/growing based on children

        frame.grid(
            row=row,
            column=column,
            rowspan=rowspan,
            columnspan=columnspan,
            padx=padx,
            pady=pady,
            sticky=sticky
        )

        return frame

    def _create_widget(self, parent, widget_def):

        widget_type = widget_def["type"]

        if widget_type not in self.registry:
            raise ValueError(f"Unknown widget type: {widget_type}")

        widget_class = self.registry[widget_type]

        properties = widget_def.get("properties", {})
        layout = widget_def.get("layout", {})

        row = layout.get("row", 0)
        column = layout.get("column", 0)
        rowspan = layout.get("rowspan", 1)
        columnspan = layout.get("columnspan", 1)

        padx = layout.get("padx", 5)
        pady = layout.get("pady", 5)

        sticky = layout.get("sticky", "nsew")

        #
        # Make grid cells expandable
        #
        for r in range(row, row + rowspan):
            parent.grid_rowconfigure(r, weight=1)

        for c in range(column, column + columnspan):
            parent.grid_columnconfigure(c, weight=1)

        #
        # Create widget
        #
        widget = widget_class(
            parent,
            **properties
        )
        widget.pack_propagate(False)  # Prevents shrinking/growing based on children
        widget.grid(
            row=row,
            column=column,
            rowspan=rowspan,
            columnspan=columnspan,
            padx=padx,
            pady=pady,
            sticky=sticky
        )

        self.widgets.append(widget)

        #
        # Optional lookup by title
        #
        title = properties.get("title")
        if title:
            self.widget_map[title] = widget

        return widget
    
    def get_widgets(self):
        return self.widgets