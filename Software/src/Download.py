import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading

ESP_IP = "http://192.168.8.175"


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

        # Scrollable list
        list_frame = ttk.Frame(root)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set
        )
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=self.listbox.yview)

        # Double-click download
        self.listbox.bind("<Double-Button-1>", lambda e: self.download_selected())

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status_var).pack(fill="x", padx=10, pady=(0, 10))

        self.refresh_logs()

    def get_logs(self):
        r = requests.get(
            f"{ESP_IP}/files",
            params={"dir": "/logs"},
            timeout=5
        )
        r.raise_for_status()

        files = r.json()

        return sorted(
            [f for f in files if f.endswith(".bin")],
            reverse=True
        )

    def refresh_logs(self):
        threading.Thread(target=self._refresh_logs, daemon=True).start()

    def _refresh_logs(self):
        try:
            self.status_var.set("Loading logs...")

            files = self.get_logs()

            self.listbox.delete(0, tk.END)

            for filename in files:
                self.listbox.insert(tk.END, filename)

            self.status_var.set(f"Found {len(files)} log files")

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

        with open(filename, "wb") as f:
            f.write(r.content)

    def download_selected(self):
        selection = self.listbox.curselection()

        if not selection:
            messagebox.showwarning("No Selection", "Please select a file.")
            return

        filename = self.listbox.get(selection[0])

        threading.Thread(
            target=self._download_file,
            args=(filename,),
            daemon=True
        ).start()

    def _download_file(self, filename):
        try:
            self.status_var.set(f"Downloading {filename}...")

            self.download_file(filename)

            self.status_var.set(f"Downloaded {filename}")

            messagebox.showinfo(
                "Success",
                f"Downloaded:\n{filename}"
            )

        except Exception as e:
            self.status_var.set("Download failed")
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = LogDownloader(root)
    root.mainloop()