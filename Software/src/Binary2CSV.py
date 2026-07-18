import struct
import csv
import os
from tkinter import filedialog
import struct
import pandas as pd
import numpy as np


MAGIC = 0xDEADBEEF

def bin_to_csv(bin_filename, create_df: bool):
    with open(bin_filename, 'rb') as bin_file:

        # -------------------------
        # HEADER
        # -------------------------
        magic = struct.unpack('<I', bin_file.read(4))[0]
        if magic != MAGIC:
            raise ValueError(f"Bad magic: {hex(magic)}")

        version = struct.unpack('<B', bin_file.read(1))[0]
        num_signals = struct.unpack('<B', bin_file.read(1))[0]

        signals = {}
        rows = []

        for _ in range(num_signals):
            sid = struct.unpack('<B', bin_file.read(1))[0]
            name_len = struct.unpack('<B', bin_file.read(1))[0]
            name = bin_file.read(name_len).decode('utf-8', errors='ignore')
            signals[sid] = name

        print(f"Version: {version}")
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

def normalize_log(
    df,
    output_csv="normalized.csv",
    hz=100,
    interpolate=True
):
    # -----------------------------------
    # Create time index
    # -----------------------------------
    timestep_ms = int(1000 / hz)

    start_time = df["timestamp_ms"].min()
    end_time = df["timestamp_ms"].max()

    timeline = np.arange(start_time, end_time + timestep_ms, timestep_ms)

    # -----------------------------------
    # Pivot signals into columns
    # -----------------------------------
    pivoted = df.pivot_table(
        index="timestamp_ms",
        columns="signal",
        values="value",
        aggfunc="last"
    )

    print("timeline length:", len(timeline))
    print("timeline start:", timeline[0])
    print("timeline end:", timeline[-1])
    print("timeline step:", timeline[1] - timeline[0])

    print(df["timestamp_ms"].min())
    print(df["timestamp_ms"].max())
    # -----------------------------------
    # Reindex onto fixed timeline
    # -----------------------------------
    pivoted = pivoted.reindex(timeline)

    # -----------------------------------
    # Fill behavior
    # -----------------------------------
    if interpolate:
        # Linear interpolation
        pivoted = pivoted.interpolate(method='linear')

        # Optional:
        # carry edges outward
        pivoted = pivoted.ffill().bfill()

    # else:
    # leave NaN values untouched

    # -----------------------------------
    # Save CSV
    # -----------------------------------
    pivoted.index.name = "timestamp_ms"

    pivoted.to_csv(output_csv)

    print(f"Saved normalized CSV: {output_csv}")

if __name__ == "__main__":

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
    
    #df = load_csv(file_path)

    normalized_filename = file_path.replace('.bin', '_Normalized.csv')

    normalize_log(
        df,
        output_csv=normalized_filename,
        hz=100,
        interpolate=True
    )