import struct
import csv
import os

MAGIC = 0xDEADBEEF

def convert_bin_to_csv(bin_filename):
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
            writer.writerow(['timestamp_ms', 'id', 'signal_name', 'value'])

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

    print(f"Done: {csv_filename}")


import struct
import pandas as pd
import numpy as np

MAGIC = 0xDEADBEEF


def load_bin(bin_filename):
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

        for _ in range(num_signals):
            sid = struct.unpack('<B', bin_file.read(1))[0]
            name_len = struct.unpack('<B', bin_file.read(1))[0]
            name = bin_file.read(name_len).decode('utf-8', errors='ignore')
            signals[sid] = name

        print(f"Version: {version}")
        print(f"Signals: {signals}")

        # -------------------------
        # DATA FORMAT
        # -------------------------
        entry_format = '<I B f'
        entry_size = struct.calcsize(entry_format)

        rows = []

        while True:
            chunk = bin_file.read(entry_size)

            if len(chunk) < entry_size:
                break

            timestamp, sensor_id, value = struct.unpack(entry_format, chunk)

            rows.append({
                "timestamp_ms": timestamp,
                "signal": signals.get(sensor_id, f"UNKNOWN_{sensor_id}"),
                "value": value
            })

    return pd.DataFrame(rows)


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
    convert_bin_to_csv('1970-01-01_02-46-42_data10.bin')

    df = load_bin("1970-01-01_02-46-42_data5.bin")

    normalize_log(
        df,
        output_csv="normalized_100hz.csv",
        hz=100,
        interpolate=True
    )