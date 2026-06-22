import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading
import os
import re
from datetime import datetime
from Binary2CSV import *
from requests_toolbelt.multipart.encoder import (
    MultipartEncoder,
    MultipartEncoderMonitor
)

class FileServerClient:
    def __init__(self, vehicle_ip):
        self.vehicle_ip = "http://" + vehicle_ip

    def get_log_number(self, filename):
        match = re.search(r"data(\d+)\.bin$", filename)
        if match:
            return int(match.group(1))
        return -1

    def get_logs(self, dir="/"):
        r = requests.get(
            f"{self.vehicle_ip}/files",
            params={"dir": dir},
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

    def download_file(self,
                    vehicle_dir,
                    filename,
                    dest_dir="",
                    progress_callback=None):

        cur_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(cur_dir, dest_dir, filename)

        with requests.get(
            f"{self.vehicle_ip}/download",
            params={"name": f"/{vehicle_dir}{filename}"},
            stream=True,
            timeout=30
        ) as r:

            r.raise_for_status()

            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=4096):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback:
                        progress_callback(downloaded, total)

        return filepath
    
    def download_file_async(self,
                            vehicle_dir,
                            filename,
                            dest_dir="",
                            progress_callback=None,
                            finished_callback=None,
                            error_callback=None):

        def worker():
            try:
                filepath = self.download_file(
                    vehicle_dir,
                    filename,
                    dest_dir,
                    progress_callback
                )

                if finished_callback:
                    finished_callback(filename, filepath)

            except Exception as e:
                if error_callback:
                    error_callback(e)

        thread = threading.Thread(
            target=worker,
            daemon=True
        )
        thread.start()

        return thread
    
    def upload_file(self,
                    local_filepath,
                    vehicle_dir="/",
                    progress_callback=None):

        filename = os.path.basename(local_filepath)

        with open(local_filepath, "rb") as f:

            encoder = MultipartEncoder(
                fields={
                    "datafile":
                        (filename,
                        f,
                        "application/octet-stream")
                }
            )

            monitor = MultipartEncoderMonitor(
                encoder,
                lambda m:
                    progress_callback(
                        m.bytes_read,
                        encoder.len
                    )
                    if progress_callback else None
            )

            r = requests.post(
                f"{self.vehicle_ip}/upload",
                params={"dir": vehicle_dir},
                data=monitor,
                headers={
                    "Content-Type":
                        monitor.content_type
                },
                timeout=60
            )

        r.raise_for_status()

        return True
    
    def upload_file_async(self,
                        local_filepath,
                        vehicle_dir="/",
                        progress_callback=None,
                        finished_callback=None,
                        error_callback=None):

        def worker():
            try:
                self.upload_file(
                    local_filepath,
                    vehicle_dir,
                    progress_callback
                )

                if finished_callback:
                    finished_callback()

            except Exception as e:
                if error_callback:
                    error_callback(e)

        thread = threading.Thread(
            target=worker,
            daemon=True
        )
        thread.start()

        return thread


class LogDownloader:
    def __init__(self, root, vehicle_ip, download_dir):
        self.root = root
        self.vehicle_ip = "http://" + vehicle_ip
        self.download_dir = download_dir

        self.fileServer = FileServerClient(vehicle_ip)

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

        os.makedirs(self.download_dir, exist_ok=True)

        self.refresh_logs()
    
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

    def refresh_logs(self):
        threading.Thread(target=self._refresh_logs, daemon=True).start()

    def _refresh_logs(self):
        try:
            self.status_var.set("Loading logs...")

            files = self.fileServer.get_logs("/logs")

            for item in self.tree.get_children():
                self.tree.delete(item)

            for filename in files:

                log_num = self.fileServer.get_log_number(filename)
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
        self.status_var.set(f"Downloading {filename}...")

        self.fileServer.download_file_async(
            "logs/",
            filename,
            self.download_dir,
            progress_callback=lambda done, total:
                self.root.after(
                    0,
                    lambda:
                        self._update_download_progress(
                            filename,
                            done,
                            total
                        )
                ),
            finished_callback=lambda filename, filepath:
                self.root.after(
                    0,
                    lambda:
                        self._download_finished(
                            filename,
                            filepath
                        )
                ),
            error_callback=lambda e:
                self.root.after(
                    0,
                    lambda:
                        self._download_failed(e)
                )
        )

    def download_selected(self):
        selected = self.tree.selection()

        if not selected:
            messagebox.showwarning(
                "No Selection",
                "Please select a file."
            )
            return

        filename = self.tree.item(
            selected[0]
        )["values"][2]

        self.download_file(filename)

    def download_latest(self):
        children = self.tree.get_children()

        if not children:
            return

        first = children[0]

        filename = self.tree.item(
            first
        )["values"][2]

        self.download_file(filename)

    def _update_download_progress(
            self,
            filename,
            downloaded,
            total
    ):
        if total > 0:
            percent = 100 * downloaded / total

            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)

            self.status_var.set(
                f"Downloading {filename} "
                f"({percent:.1f}% - "
                f"{mb_done:.2f}/{mb_total:.2f} MB)"
            )
        else:
            self.status_var.set(
                f"Downloading {filename} "
                f"({downloaded / (1024 * 1024):.2f} MB)"
            )

    def _download_finished(
            self,
            filename,
            filepath
    ):
        self.status_var.set(
            f"Downloaded {filename}"
        )

        messagebox.showinfo(
            "Success",
            f"Downloaded:\n{filepath}"
        )

        df = load_bin(filepath, True)

        normalized_filename = filepath.replace('.bin', '_Normalized.csv')

        normalize_log(
            df,
            output_csv=normalized_filename,
            hz=100,
            interpolate=True
        )

    def _download_failed(self, error):
        self.status_var.set(
            "Download failed"
        )

        messagebox.showerror(
            "Error",
            str(error)
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = LogDownloader(root, "192.168.8.175", "/logs")
    root.mainloop()