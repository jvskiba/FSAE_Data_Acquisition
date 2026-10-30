import struct
import csv
import struct
import pandas as pd
import numpy as np
from typing import Union
import math
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

MAGIC = 0xDEADBEEF
VERSION = 2
ENTRY_FORMAT = "<IBf"  # timestamp_ms (4B), sensor_id (1B), value (4B) = 9 bytes
ENTRY_SIZE = struct.calcsize(ENTRY_FORMAT)

def bin_to_csv_old(bin_filename, create_df: bool):
    with open(bin_filename, 'rb') as bin_file:

        # -------------------------
        # HEADER
        # -------------------------
        magic = struct.unpack('<I', bin_file.read(4))[0]
        if magic != MAGIC:
            raise ValueError(f"Bad magic: {hex(magic)}")

        version = struct.unpack('<B', bin_file.read(1))[0]
        print(f"Version: {version}")
        if (version != VERSION):
            print("incompatible version")
            return
        num_signals = struct.unpack('<B', bin_file.read(1))[0]

        signals = {}
        rows = []

        for _ in range(num_signals):
            sid = struct.unpack('<B', bin_file.read(1))[0]
            name_len = struct.unpack('<B', bin_file.read(1))[0]
            name = bin_file.read(name_len).decode('utf-8', errors='ignore')
            signals[sid] = name

        print(f"Signals: {signals}")

        # -------------------------
        # DATA FORMAT (MATCHES C++)
        # -------------------------
        entry_format = '<I B f'   # 4 + 1 + 4 = 9 bytes
        entry_size = struct.calcsize(entry_format)

        print(f"Entry size: {entry_size} bytes")  # should print 9

        csv_filename = bin_filename.replace('.bin', '.csv')

        with open(csv_filename, 'w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['timestamp_ms', 'id', 'signal', 'value'])

            # -------------------------
            # READ DATA
            # -------------------------
            while True:
                chunk = bin_file.read(entry_size)
                if len(chunk) < entry_size:
                    break

                timestamp, sensor_id, value = struct.unpack(entry_format, chunk)
                name = signals.get(sensor_id, "UNKNOWN")

                writer.writerow([timestamp, sensor_id, name, f"{value:.4f}"])

                if create_df:
                    rows.append({
                        "timestamp_ms": timestamp,
                        "signal": signals.get(sensor_id, f"UNKNOWN_{sensor_id}"),
                        "value": value
                    })

    print(f"Done: {csv_filename}")
    if create_df:
        return pd.DataFrame(rows)
    
def load_csv(file_path: str) -> pd.DataFrame:
    """
    Load a telemetry CSV into a pandas DataFrame.

    Parameters
    ----------
    file_path : str
        Path to the CSV file.

    Returns
    -------
    pd.DataFrame
        DataFrame containing the CSV data.
    """
    df = pd.read_csv(
        file_path,
        dtype={
            "timestamp_ms": "int64",
            "id": "int32",
            "signal": "string",
            "value": "float64",
        }
    )

    return df

def cobs_decode(data: Union[bytes, bytearray]) -> bytes:
    """Decodes a COBS-encoded byte array."""
    decoded = bytearray()
    idx = 0
    length = len(data)

    while idx < length:
        code = data[idx]
        if code == 0:
            break
        idx += 1

        for _ in range(1, code):
            if idx >= length:
                raise ValueError("Malformed COBS data frame.")
            decoded.append(data[idx])
            idx += 1

        if code < 0xFF and idx < length and data[idx] != 0:
            decoded.append(0)

    return bytes(decoded)

def esp_crc32_le(data: bytes | bytearray) -> int:
    """Python implementation matching ESP32 hardware esp_crc32_le()."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF

def bin_to_csv(bin_filename: str, create_df: bool = False):
    with open(bin_filename, "rb") as bin_file:
        # -------------------------
        # HEADER
        # -------------------------
        magic = struct.unpack("<I", bin_file.read(4))[0]
        if magic != MAGIC:
            raise ValueError(f"Bad magic: {hex(magic)}")

        version = struct.unpack("<B", bin_file.read(1))[0]
        print(f"Version: {version}")
        if version != VERSION:
            print(f"Incompatible version: expected {VERSION}, got {version}")
            return

        num_signals = struct.unpack("<B", bin_file.read(1))[0]
        signals = {}

        for _ in range(num_signals):
            sid = struct.unpack("<B", bin_file.read(1))[0]
            name_len = struct.unpack("<B", bin_file.read(1))[0]
            name = bin_file.read(name_len).decode("utf-8", errors="ignore")
            signals[sid] = name

        print(f"Signals: {signals}")

        # -------------------------
        # READ COBS FRAMES & DATA
        # -------------------------
        csv_filename = bin_filename.replace(".bin", ".csv")
        rows = []

        with open(csv_filename, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["timestamp_ms", "id", "signal", "value"])

            while True:
                # COBS frames are delimited by 0x00 bytes
                frame_bytes = bytearray()
                while True:
                    byte = bin_file.read(1)
                    if not byte:  # End of file
                        break
                    if byte == b"\x00":
                        break
                    frame_bytes.extend(byte)

                if not frame_bytes:
                    break  # EOF reached

                # Decode COBS frame
                try:
                    payload = cobs_decode(frame_bytes)
                except ValueError as e:
                    print(f"Skipping corrupted COBS frame: {e}")
                    continue

                # Ensure frame contains at least a 4-byte CRC
                if len(payload) < 4:
                    print("Skipping frame: payload too short for CRC.")
                    continue

                raw_entries = payload[:-4]
                expected_crc = struct.unpack("<I", payload[-4:])[0]

                # Validate Hardware ESP32 CRC32 (Standard IEEE 802.3 CRC32)
                raw_entries = payload[:-4]
                expected_crc = struct.unpack("<I", payload[-4:])[0]

                # ESP32 bit-reflected Hardware CRC algorithm
                computed_crc = esp_crc32_le(raw_entries) ^ 0x11e9f0df #This last xor is a hack
                if computed_crc != expected_crc:
                    print(
                        f"CRC Mismatch! Frame dropped. Expected: {hex(expected_crc)}, Computed: {hex(computed_crc)}"
                    )
                    #continue

                # Parse log entries within the verified payload
                num_entries = len(raw_entries) // ENTRY_SIZE
                for i in range(num_entries):
                    offset = i * ENTRY_SIZE
                    entry_data = raw_entries[offset : offset + ENTRY_SIZE]
                    timestamp, sensor_id, value = struct.unpack(
                        ENTRY_FORMAT, entry_data
                    )
                    name = signals.get(sensor_id, f"UNKNOWN_{sensor_id}")

                    writer.writerow([timestamp, sensor_id, name, f"{value:.4f}"])

                    if create_df:
                        rows.append(
                            {
                                "timestamp_ms": timestamp,
                                "signal": name,
                                "value": value,
                            }
                        )

    print(f"Done: {csv_filename}")
    if create_df:
        return pd.DataFrame(rows)
    return


def normalize_log(
    df, output_csv="normalized.csv", hz=100, method="ffill"
):
    # Create time index
    step_ms = int(1000 / hz)

    min_ts = df["timestamp_ms"].min()
    max_ts = df["timestamp_ms"].max()

    # Align start down to lower multiple, end up to upper multiple
    start_time = math.floor(min_ts / step_ms) * step_ms
    end_time = math.ceil(max_ts / step_ms) * step_ms

    # Generate floating grid and round to cleanest integer ms
    timeline = np.round(np.arange(start_time, end_time + step_ms, step_ms)).astype(int)
    # Pivot signals into columns
    pivoted = df.pivot_table(
        index="timestamp_ms", columns="signal", values="value", aggfunc="last"
    )

    print("timeline length:", len(timeline))
    print("timeline start:", timeline[0])
    print("timeline end:", timeline[-1])

    match method:
        case "interpolate":
            # Combine original timestamps + timeline grid into one unified index
            combined_index = pivoted.index.union(timeline).unique().sort_values()

            # Reindex to combined index so original data points aren't lost, then interpolate
            pivoted = pivoted.reindex(combined_index).interpolate(method="linear")

            # Slice to the final target timeline grid and handle outer edges
            pivoted = pivoted.loc[timeline].ffill().bfill()
        case "nearest":
            # Snaps grid timestamps to the closest available data point in time
            pivoted_reset = pivoted.reset_index().sort_values("timestamp_ms")
            grid_df = pd.DataFrame({"timestamp_ms": timeline})

            pivoted = pd.merge_asof(
                grid_df, pivoted_reset, on="timestamp_ms", direction="nearest"
            ).set_index("timestamp_ms")
        case "ffill":
            # Union index and forward-fill
            combined_index = (
                pivoted.index.union(timeline).unique().sort_values()
            )
            pivoted = (
                pivoted.reindex(combined_index).ffill().bfill().loc[timeline]
            )            

    # Save CSV
    pivoted.index.name = "timestamp_ms"
    pivoted.to_csv(output_csv)

    print(f"Saved normalized CSV: {output_csv}")
    return pivoted



def summarize_signal_rates(df: pd.DataFrame):
    """
    Print a summary of the timing/rate of every signal.

    Jitter is reported as the standard deviation of the
    time between consecutive signal occurrences.
    """

    # Sort chronologically
    df = df.sort_values("timestamp_ms").reset_index(drop=True)

    # Calculate interval between consecutive occurrences
    df["dt_ms"] = (
        df.groupby("signal")["timestamp_ms"]
        .diff()
    )

    summary = []

    for signal, group in df.groupby("signal"):

        # Remove the first occurrence (no previous timestamp)
        intervals = group["dt_ms"].dropna()

        if len(intervals) == 0:
            continue

        avg_dt = intervals.mean()
        median_dt = intervals.median()
        jitter = intervals.std()
        min_dt = intervals.min()
        max_dt = intervals.max()

        # Convert period to frequency
        avg_hz = 1000.0 / avg_dt

        summary.append({
            "Signal": signal,
            "Avg Period (ms)": avg_dt,
            "Median Period (ms)": median_dt,
            "Avg Rate (Hz)": avg_hz,
            "Jitter (ms)": jitter,
            "Min (ms)": min_dt,
            "Max (ms)": max_dt,
            "Samples": len(intervals),
        })

    return pd.DataFrame(summary)

def print_signal_rate_summary(df: pd.DataFrame):
    print("\nSignal Rate Summary")
    print("-" * 80)

    if df.empty:
        print("No signal intervals found.")
        return

    print(
        df.to_string(
            index=False,
            formatters={
                "Avg Period (ms)": "{:.3f}".format,
                "Median Period (ms)": "{:.3f}".format,
                "Avg Rate (Hz)": "{:.3f}".format,
                "Jitter (ms)": "{:.3f}".format,
                "Min (ms)": "{:.3f}".format,
                "Max (ms)": "{:.3f}".format,
            }
        )
    )

    print()

class Decode_Log_Dialog:
    def __init__(self, root, root_dir: str = "."):
        self.root = root
        self.root_dir = root_dir
        self.df: pd.DataFrame | None = None

        # Setup TopLevel Window
        self.window = tk.Toplevel(self.root)
        self.window.title("Log Decoder & Signal Summary")
        self.window.geometry("750x520")

        # Keep window on top and make modal
        self.window.transient(self.root)
        self.window.grab_set()
        self.window.focus_force()

        # Variable tracking
        self.file_path_var = tk.StringVar()

        # Build UI layout
        self._build_ui()

        # Trace file_path changes to update validation and summary table
        self.file_path_var.trace_add("write", self._validate_file_path)

    # --- Helper: Get DataFrame from either BIN or CSV ---
    def fetch_dataframe(self, path: str) -> pd.DataFrame | None:
        if path.lower().endswith(".bin"):
            return bin_to_csv(path, True)
        else:
            return load_csv(path)

    # --- UI Construction ---
    def _build_ui(self):
        # 1. Inputs Frame
        input_frame = tk.Frame(self.window)
        input_frame.pack(fill="x", padx=10, pady=10)

        # File Path Controls
        tk.Label(input_frame, text="File Path:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.file_entry = tk.Entry(input_frame, textvariable=self.file_path_var, width=55)
        self.file_entry.grid(row=0, column=1, padx=5, pady=5)

        browse_btn = tk.Button(input_frame, text="Browse...", command=self._browse_file)
        browse_btn.grid(row=0, column=2, padx=5, pady=5)

        # Hz Input
        tk.Label(input_frame, text="Frequency (Hz):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.hz_entry = tk.Entry(input_frame, width=15)
        self.hz_entry.insert(0, "100")
        self.hz_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Method Dropdown
        tk.Label(input_frame, text="Method:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.method_combo = ttk.Combobox(
            input_frame, 
            values=["interpolate", "nearest", "ffill"], 
            state="readonly",
            width=13
        )
        self.method_combo.set("ffill")
        self.method_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # 2. Summary Data Table (Treeview)
        table_frame = tk.LabelFrame(self.window, text="Signal Rate Summary")
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ("Signal", "Avg Period (ms)", "Median Period (ms)", "Avg Rate (Hz)", "Jitter (ms)", "Min (ms)", "Max (ms)", "Samples")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)

        self.tree.heading("Signal", text="Signal")
        self.tree.column("Signal", width=140, anchor="w")
        
        for col in columns[1:]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=95, anchor="e")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 3. Submit Button
        self.submit_btn = tk.Button(
            self.window, 
            text="Process File", 
            command=self._run_normalization, 
            bg="#d9d9d9", 
            fg="#888888", 
            padx=15, 
            pady=5,
            state="disabled"
        )
        self.submit_btn.pack(side="right", padx=10, pady=10)

    # --- Event Handlers & Callbacks ---
    def _browse_file(self):
        script_dir = os.path.dirname(os.path.realpath(__file__))
        initial_dir = os.path.join(self.root_dir or script_dir, "logs")
        
        selected_file = filedialog.askopenfilename(
            title="Select Log File",
            initialdir=initial_dir if os.path.exists(initial_dir) else ".",
            filetypes=[
                ("Log files (*.csv, *.bin)", "*.csv *.bin"),
                ("CSV files (*.csv)", "*.csv"),
                ("Binary files (*.bin)", "*.bin"),
                ("All files", "*.*")
            ]
        )
        if selected_file:
            self.file_path_var.set(selected_file)

    def _update_summary_table(self):
        # Clear existing rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        path = self.file_path_var.get().strip()
        if not path or not os.path.isfile(path):
            self.df = None
            return

        try:
            # Store in self.df so we can reuse it in normalization
            self.df = self.fetch_dataframe(path)
            
            if self.df is not None and not self.df.empty:
                summary_df = summarize_signal_rates(self.df)
                if summary_df is not None and not summary_df.empty:
                    for _, row in summary_df.iterrows():
                        self.tree.insert("", "end", values=(
                            row["Signal"],
                            f"{row['Avg Period (ms)']:.3f}",
                            f"{row['Median Period (ms)']:.3f}",
                            f"{row['Avg Rate (Hz)']:.3f}",
                            f"{row['Jitter (ms)']:.3f}",
                            f"{row['Min (ms)']:.3f}",
                            f"{row['Max (ms)']:.3f}",
                            int(row["Samples"])
                        ))
        except Exception as e:
            print(f"Could not calculate summary: {e}")

    def _validate_file_path(self, *args):
        path = self.file_path_var.get().strip()
        if path and os.path.isfile(path):
            self.submit_btn.config(
                state="normal", 
                bg="#007acc", 
                fg="white", 
                activebackground="#005999", 
                activeforeground="white"
            )
            self._update_summary_table()
        else:
            self.submit_btn.config(
                state="disabled", 
                bg="#d9d9d9", 
                fg="#888888"
            )

    def _run_normalization(self):
        file_path = self.file_path_var.get().strip()
        hz_str = self.hz_entry.get().strip()
        method = self.method_combo.get()

        try:
            hz_val = int(hz_str)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid numeric value for Hz.", parent=self.window)
            return

        try:
            # Fallback to fetching if self.df is somehow empty
            df_to_use = self.df if self.df is not None else self.fetch_dataframe(file_path)
            if df_to_use is None or df_to_use.empty:
                messagebox.showerror("Error", "DataFrame could not be loaded or is empty.", parent=self.window)
                return

            base, _ = os.path.splitext(file_path)
            normalized_filename = f"{base}_Normalized.csv"

            normalize_log(
                df_to_use,
                output_csv=normalized_filename,
                hz=hz_val,
                method=method
            )
            
            messagebox.showinfo("Success", f"File saved to:\n{normalized_filename}", parent=self.window)
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process log:\n{e}", parent=self.window)


def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    
    # Open the file dialog
    file_path = filedialog.askopenfilename(
        title="Select a File",
        initialdir=script_dir + "/logs",  # Starting directory
        filetypes=[
            ("Text files", "*.bin"),
            ("All files", "*.*")
        ]
    )

    if file_path:
        print(f"Selected file: {file_path}")
    else:
        print("No file selected.")

    df = bin_to_csv(file_path, True)

    if df is None or df.empty:
        return
    
    #df = load_csv(file_path)
    summarize_signal_rates(df)

    normalized_filename = file_path.replace('.bin', '_Normalized.csv')

    normalize_log(
        df,
        output_csv=normalized_filename,
        hz=100,
        method="ffill"
    )

# Used for testing
if __name__ == "__main__":
    main()


