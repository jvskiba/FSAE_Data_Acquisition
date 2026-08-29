import struct
import csv
import os
from tkinter import filedialog
import struct
import pandas as pd
import numpy as np
import zlib
from typing import Union


MAGIC = 0xDEADBEEF
VERSION = 2

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



ENTRY_FORMAT = "<IBf"  # timestamp_ms (4B), sensor_id (1B), value (4B) = 9 bytes
ENTRY_SIZE = struct.calcsize(ENTRY_FORMAT)


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