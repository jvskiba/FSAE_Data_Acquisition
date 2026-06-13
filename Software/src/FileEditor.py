import tkinter as tk

class FileEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Untitled - Text Editor")
        self.file_path = None

        # Text Widget
        self.text_widget = tk.Text(root, wrap='word')
        self.text_widget.pack(expand=True, fill='both')
        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack()

        self.cancel_btn = tk.Button(self.btn_frame, text="Cancel", command=root.destroy)
        self.cancel_btn.pack(pady=5, side=tk.LEFT)
        self.save_btn = tk.Button(self.btn_frame, text="Save & Close", command=self.save_file)
        self.save_btn.pack(pady=5, side=tk.LEFT)
        

    def open_file(self, file_path):
        if file_path:
            with open(file_path, 'r') as file:
                self.text_widget.delete(1.0, tk.END)
                self.text_widget.insert(tk.END, file.read())
            self.file_path = file_path

    def save_file(self):
        if self.file_path:
            self._write_to_file(self.file_path)

        self.root.destroy()

    def _write_to_file(self, path):
        content = self.text_widget.get(1.0, tk.END)
        with open(path, 'w') as file:
            file.write(content)   