import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont
import queue
from tkinter import filedialog
import math
import time

from Device_Manager import *
from GUI_Widgets import *
from ConfigManager import *
from FileEditor import *
from LayoutBuilder import *
from Binary2CSV import *
from Download import *

# ======================================================
# GUI (View Only)
# ======================================================
class TelemetryDashboard:
    def __init__(self, root, controller: TelemetryController, configManager: ConfigManager):
        self.root = root
        self.controller = controller
        self.configManager = configManager
        self.config = configManager.config

        root.title("JvS Data Aquisition App")
        root.geometry("1400x900")
        root.minsize(1200, 800)

        self.build_top_menu()

        self.layout_manager = LayoutManager(root, widget_registry)
        self.layout_file = self.config.main.layout_file
        self.layout_manager.load_layout(self.layout_file)
        self.gui_elements = self.layout_manager.get_widgets()
        
        # Start queue processing loop
        self.root.after(100, self.process_gui_queue)
        self.last_update = time.monotonic()

    def build_top_menu(self):
        self.menu_font = tkFont.Font(size=16)

        self.menubar = tk.Menu(self.root)       

        # File Menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.config(font=self.menu_font)
        file_menu.add_command(label="Edit Config", command=self.editConfig)
        #file_menu.add_command(label="Reload Config", command=self.configManager.load) #TODO: Currently not really working
        file_menu.add_command(label="Edit Layout", command=self.editLayout)
        file_menu.add_command(label="Reload Layout", command=self.reload_layout)
        file_menu.add_command(label="Open Layout", command=self.open_layout)
        file_menu.add_command(label="Open 2nd Window - Buggy", command=self.open_2nd_window)
        file_menu.add_command(label="Decode Log", command=self.decode_binary)
        file_menu.add_command(label="Open Command Page", command=self.open_cmd_page)
        file_menu.add_command(label="Browse Logs", command=self.open_download_page)
        file_menu.add_command(label="Vehicle Config", command=self.open_config_edit_page)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)

        self.menubar.add_cascade(label="File", menu=file_menu)

        # Logging Menu
        log_menu = tk.Menu(self.menubar, tearoff=0)
        log_menu.config(font=self.menu_font)
        log_menu.add_command(label="Start Local Log", command=self.temp)
        log_menu.add_command(label="Stop Local Log", command=self.temp)
        log_menu.add_command(label="Browse Logs", command=self.open_download_page)
        log_menu.add_command(label="Normalize Log", command=self.decode_csv)
        log_menu.add_command(label="View Log", command=self.temp)

        self.menubar.add_cascade(label="Logging", menu=log_menu)

        self.root.config(menu=self.menubar)

    def temp(self):
        print("not implemented yet")
        return 

    def open_layout(self):
        file_path = filedialog.askopenfilename(title="Select a file")
        print(f"Selected: {file_path}")
        self.layout_file = file_path
        self.reload_layout()
        return

    def reload_layout(self):
        self.layout_manager.clear_layout()
        self.layout_manager.load_layout(self.layout_file)
        self.gui_elements = self.layout_manager.get_widgets()
        return
    
    def open_2nd_window(self):
        new_window = tk.Toplevel(root)
        new_window.title("JvS Data Aquisition App")
        new_window.geometry("1400x900")


        layout_manager = LayoutManager(new_window, widget_registry)
        layout_manager.load_layout("layout.json")
        self.gui_elements.extend(layout_manager.get_widgets())
        return

    def editConfig(self):
        new_window = tk.Toplevel(root)
        new_window.title("Config Editor")
        new_window.geometry("800x600")

        editor = FileEditor(new_window)
        editor.open_file("config.json")
        return
    
    def editLayout(self):
        new_window = tk.Toplevel(root)
        new_window.title("Layout Editor")
        new_window.geometry("800x600")

        editor = FileEditor(new_window)
        editor.open_file("layout.json")
        return
    
    def decode_csv(self):
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Open the file dialog
        file_path = filedialog.askopenfilename(
            title="Select a File",
            initialdir=script_dir + "/logs",  # Starting directory
            filetypes=[
                ("Text files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            print(f"Selected file: {file_path}")
        else:
            print("No file selected.")

        df = load_csv(file_path)

        normalized_filename = file_path.replace('.csv', '_Normalized.csv')

        normalize_log(
            df,
            output_csv=normalized_filename,
            hz=100,
            interpolate=True
        )
    
    def open_download_page(self):
        new_window = tk.Toplevel(root)
        new_window.title("Log Downloader")
        new_window.geometry("800x600")
        
        en_name = "Enable_FileServer"
        en_cmd = self.config.cmds.commands.get(en_name)

        dis_name = "Disable_FileServer"
        dis_cmd = self.config.cmds.commands.get(dis_name)

        if not en_cmd or not dis_cmd:
            print("Fileserver Commands not found")
            return

        self.controller.send_cmd_async(en_name, en_cmd)
        cwd = os.getcwd()
        LogDownloader(new_window, self.config.main.vehicle_ip, cwd + "\\logs")

        def close_window():
            self.controller.send_cmd_async(dis_name, dis_cmd)
            new_window.destroy()
            return
        
        new_window.protocol("WM_DELETE_WINDOW", close_window)
        return
    
    def open_config_edit_page(self):
        new_window = tk.Toplevel(root)
        new_window.title("Vehicle Config Editor")
        new_window.geometry("800x600")
        
        en_name = "Enable_FileServer"
        en_cmd = self.config.cmds.commands.get(en_name)

        dis_name = "Disable_FileServer"
        dis_cmd = self.config.cmds.commands.get(dis_name)

        if not en_cmd or not dis_cmd:
            print("Fileserver Commands not found")
            return

        self.controller.send_cmd_async(en_name, en_cmd)
        fileServer = FileServerClient(config.main.vehicle_ip)

        status_var = tk.StringVar(value="Ready")

        # Top controls
        top_frame = ttk.Frame(new_window)
        top_frame.pack(fill="x", padx=10, pady=10)

        def download():
            status_var.set("Downloading...")
            new_window.update_idletasks()

            def _download_finished(filename, filepath):
                status_var.set(f"Downloaded {filename}")

            def _download_failed(error):
                status_var.set("Download failed")

                messagebox.showerror("Error", str(error))

            fileServer.download_file_async("/", "config.json", "vehicle_config/", 
                finished_callback=lambda filename, filepath:
                    self.root.after(
                        0,
                        lambda:
                            _download_finished(
                                filename,
                                filepath
                            )
                    ),
                error_callback=lambda e:
                    self.root.after(
                        0,
                        lambda:
                            _download_failed(e)
                    ))

            editor.open_file("vehicle_config/config.json")

        ttk.Button(
            top_frame,
            text="Download Config File",
            command=download
        ).pack(side="left")

        def upload():
            editor.save_file()
            fileServer.upload_file_async("vehicle_config/config.json")

        ttk.Button(
            top_frame,
            text="Upload Config File",
            command=upload
        ).pack(side="left", padx=5)

        ttk.Label(
            top_frame,
            textvariable=status_var
        ).pack(side="right")

        # File Editor
        edit_frame = ttk.Frame(new_window)
        edit_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        editor = FileEditor(edit_frame)
        editor.open_file("vehicle_config/config.json")

        def close_window():
            self.controller.send_cmd_async(dis_name, dis_cmd)
            new_window.destroy()
            return
        
        new_window.protocol("WM_DELETE_WINDOW", close_window)
        return
    
    def open_cmd_page(self):
        new_window = tk.Toplevel(root)
        new_window.title("Command Page")
        new_window.geometry("800x600")

        menu = CommandMenu(
            new_window,
            self.configManager,
            command_callback=self.controller.send_cmd_async
        )
        menu.pack(fill="both", expand=True, padx=10, pady=10)

    def build_control_ui(self, parent):
        ttk.Label(parent, text="Marker:").pack()
        self.marker_entry = ttk.Entry(parent)
        self.marker_entry.pack()
        ttk.Button(
            parent,
            text="Add Marker",
            command=lambda: (self.controller.add_marker(self.marker_entry.get()), self.marker_entry.delete(0, tk.END)),
        ).pack(pady=5)

        def send_command_lora():
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
            s.connect((self.config.main.vehicle_ip, self.config.main.vehicle_port))

            packet = (
                itv_cmd(0x01, 5) +
                itv_u8(0x02, 1)
            )

            s.sendall(packet)
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
            command=send_command_lora,
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
        
        self.update(self.controller.signals.get_latest_telem())
    
        # reschedule
        if self.controller.running:
            delay = int(1000/self.config.main.framerate)
            self.root.after(delay, self.process_gui_queue)

    # ------------------------------
    def update(self, row: dict):
        for elmt in self.gui_elements:
            elmt.update_data(row)

    # ------------------------------
    # Optional demo generator
    # ------------------------------
    def scale_sin(self, t, min_val, max_val, freq=1.0):
        """
        Maps a sine wave to a range.
        freq = cycles per second
        """
        s = (math.sin(t * freq) + 1) / 2
        return min_val + s * (max_val - min_val)

    def demo_update(self):
        t = time.time()

        rpm = (
            self.scale_sin(t, 800, 12000, 0.15)
            + 500 * math.sin(t * 4.0)
            + 150 * math.sin(t * 11.0)
        )

        self.controller.signals.update(
            "RPM",
            rpm
        )

        self.controller.signals.update(
            "VSS",
            int(self.scale_sin(t, 0, 150, 0.2))
        )

        self.controller.signals.update(
            "STR",
            int(self.scale_sin(t, -100, 100, 1.5))
        )

        self.controller.signals.update(
            "TPS",
            self.scale_sin(t, 0, 100, 2.0)
        )

        self.controller.signals.update(
            "BPS1",
            self.scale_sin(t + 1.0, 0, 100, 1.7)
        )

        self.controller.signals.update(
            "AccelX",
            self.scale_sin(t, -2, 2, 4.0)
        )

        self.controller.signals.update(
            "AccelY",
            self.scale_sin(t + 2.0, -2, 2, 3.5)
        )

        self.controller.signals.update(
            "MAT",
            self.scale_sin(t, -100, 0, 0.05)
        )

        self.controller.signals.update(
            "BatV",
            self.scale_sin(t, 11.8, 14.5, 0.1)
        )

        self.controller.signals.update(
            "CLT1",
            self.scale_sin(t, 70, 105, 0.03)
        )

        self.controller.signals.update(
            "CLT2",
            self.scale_sin(t + 5, 70, 105, 0.03)
        )

        self.controller.signals.update(
            "OilTemp",
            self.scale_sin(t, 80, 120, 0.02)
        )

        self.controller.signals.update(
            "AirTemp",
            self.scale_sin(t, 20, 45, 0.05)
        )

        self.controller.signals.update(
            "FuelPres",
            self.scale_sin(t, 35, 55, 0.8)
        )

        self.controller.signals.update(
            "OilPres",
            self.scale_sin(t, 25, 75, 1.0)
        )

        self.controller.signals.update(
            "AFR",
            self.scale_sin(t, 12.5, 15.0, 1.2)
        )

        self.controller.signals.update(
            "Yaw",
            self.scale_sin(t, -20, 20, 0.7)
        )

        self.controller.signals.update(
            "Pitch",
            self.scale_sin(t + 1.5, -10, 10, 0.8)
        )

        self.controller.signals.update(
            "Roll",
            self.scale_sin(t + 3.0, -15, 15, 0.9)
        )

        # Simulated gear based on RPM
        gear = min(6, max(1, int((rpm - 800) / 1900) + 1))
        self.controller.signals.update("Gear", gear)

        root.after(10, self.demo_update)

class CommandMenu(tk.LabelFrame):
    def __init__(self, parent, config_manager, command_callback=None, **kwargs):
        super().__init__(parent, text="Commands", **kwargs)

        self.config_manager = config_manager
        self.command_callback = command_callback

        self.button_frame = tk.Frame(self)
        self.button_frame.pack(fill="both", expand=True)

        # Register for config updates
        self.config_manager.register_listener(self.update_commands)

        # Build initial buttons
        self.update_commands(self.config_manager.config)

    def update_commands(self, config):
        # Remove old buttons
        for widget in self.button_frame.winfo_children():
            widget.destroy()

        # Create new buttons
        for row, (name, cmd) in enumerate(config.cmds.commands.items()):

            btn = tk.Button(
                self.button_frame,
                text=name,
                command=lambda n=name, c=cmd: self.run_command(n, c)
            )

            btn.grid(row=row, column=0, sticky="ew", padx=2, pady=2)

        self.button_frame.grid_columnconfigure(0, weight=1)

    def run_command(self, name, cmd):
        print(
            f"Command: {name} "
            f"(ID={cmd.ID}, Data={cmd.Data})"
        )

        if self.command_callback:
            self.command_callback(name, cmd)


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
    if (False):
        dashboard.demo_update()
        #dashboard.demo_update_time()
    # Clean exit
    def stop():
        controller.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", controller.stop)

    root.mainloop()


