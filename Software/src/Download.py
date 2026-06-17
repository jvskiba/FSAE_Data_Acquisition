import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading

ESP_IP = "http://192.168.8.175"

import os
import re
from datetime import datetime

DOWNLOAD_DIR = "logs"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


class LogDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP Log Downloader")
        self.root.geometry("500x400")

        # Top controls
        top_frame = ttk.Frame(root)
        top_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            top_frame,
            text="Refresh",
            command=self.refresh_logs
        ).pack(side="left")

        ttk.Button(
            top_frame,
            text="Download Selected",
            command=self.download_selected
        ).pack(side="left", padx=5)

        ttk.Button(
            top_frame,
            text="Download Latest",
            command=self.download_latest
        ).pack(side="left", padx=5)

        # Scrollable list
        list_frame = ttk.Frame(root)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(
            list_frame,
            columns=("lognum", "date", "filename", "size"),
            show="headings"
        )

        self.tree.heading("lognum", text="Log #")
        self.tree.heading("date", text="Date")
        self.tree.heading("filename", text="Filename")
        #self.tree.heading("size", text="Size")

        self.tree.column("lognum", width=80, anchor="center")
        self.tree.column("date", width=170)
        self.tree.column("filename", width=250)
        #self.tree.column("size", width=80, anchor="e")

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview
        )

        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status_var).pack(fill="x", padx=10, pady=(0, 10))

        self.refresh_logs()

    def get_log_number(self, filename):
        match = re.search(r"data(\d+)\.bin$", filename)
        if match:
            return int(match.group(1))
        return -1
    
    def get_log_date(self, filename):
        try:
            timestamp = filename.split("_data")[0]

            dt = datetime.strptime(
                timestamp,
                "%Y-%m-%d_%H-%M-%S"
            )

            return dt.strftime("%Y-%m-%d %H:%M:%S")

        except:
            return "Unknown"

    def get_logs(self):
        r = requests.get(
            f"{ESP_IP}/files",
            params={"dir": "/logs"},
            timeout=5
        )
        r.raise_for_status()

        files = r.json()

        bin_files = [f for f in files if f.endswith(".bin")]

        return sorted(
            bin_files,
            key=self.get_log_number,
            reverse=True
        )

    def refresh_logs(self):
        threading.Thread(target=self._refresh_logs, daemon=True).start()

    def _refresh_logs(self):
        try:
            self.status_var.set("Loading logs...")

            files = self.get_logs()

            for item in self.tree.get_children():
                self.tree.delete(item)

            for filename in files:

                log_num = self.get_log_number(filename)
                log_date = self.get_log_date(filename)

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        log_num,
                        log_date,
                        filename
                    )
                )

            self.status_var.set(f"Found {len(files)} log files") #TODO: Displaying wrong number I think

        except Exception as e:
            self.status_var.set("Failed to load logs")
            messagebox.showerror("Error", str(e))

    def download_file(self, filename):
        r = requests.get(
            f"{ESP_IP}/download",
            params={"name": f"/logs/{filename}"},
            timeout=30
        )
        r.raise_for_status()

        filepath = os.path.join(DOWNLOAD_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(r.content)
        
        return filepath

    def download_selected(self):
        selected = self.tree.selection()

        if not selected:
            messagebox.showwarning("No Selection", "Please select a file.")
            return

        filename = self.tree.item(
            selected[0]
        )["values"][2]


        threading.Thread(
            target=self._download_file,
            args=(filename,),
            daemon=True
        ).start()

    def _download_file(self, filename):
        try:
            self.status_var.set(f"Downloading {filename}...")

            filepath = self.download_file(filename)

            self.status_var.set(f"Downloaded {filename}")

            messagebox.showinfo(
                "Success",
                f"Downloaded:\n{filepath}"
            )

        except Exception as e:
            self.status_var.set("Download failed")
            messagebox.showerror("Error", str(e))

    def download_latest(self):
        first = self.tree.get_children()[0]

        filename = self.tree.item(
            first
        )["values"][2]

        threading.Thread(
            target=self._download_file,
            args=(first,),
            daemon=True
        ).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = LogDownloader(root)
    root.mainloop()