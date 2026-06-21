import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

class FileEditor:
    def __init__(self, root):
        self.root = root
        self.file_path = None

        self.font = tkFont.Font(size=16)

        self.status_var = tk.StringVar(value="Ready")

        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        self.text_widget = tk.Text(root, wrap='word', font=self.font)
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(root, orient="vertical")

        scrollbar.grid(row=0, column=1, sticky="ns")
        scrollbar.config(command=self.text_widget.yview)

        self.btn_frame = tk.Frame(root)
        self.btn_frame.grid(row=1, column=0, sticky="ew")

        ttk.Label(
            self.btn_frame,
            textvariable=self.status_var
        ).pack(side="left")

        self.save_btn = tk.Button(
            self.btn_frame,
            text="Save",
            command=self.save_file
        )
        self.save_btn.pack(side=tk.RIGHT, padx=(5,10), pady=5)

        self.cancel_btn = tk.Button(
            self.btn_frame,
            text="Cancel",
            command=self.reload_file
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        
    def reload_file(self):
        if self.file_path: 
            self.open_file(self.file_path)

    def open_file(self, file_path):
        if file_path:
            with open(file_path, 'r') as file:
                self.text_widget.delete(1.0, tk.END)
                self.text_widget.insert(tk.END, file.read())
            self.file_path = file_path
            self.status_var.set("Opened: " + file_path)
        else:
            self.status_var.set("No File")

    def save_file(self):
        if self.file_path:
            self._write_to_file(self.file_path)
            self.status_var.set("Saved: " + self.file_path)
        else:
            self.status_var.set("No File")

    def _write_to_file(self, path):
        content = self.text_widget.get(1.0, tk.END)
        with open(path, 'w') as file:
            file.write(content)   