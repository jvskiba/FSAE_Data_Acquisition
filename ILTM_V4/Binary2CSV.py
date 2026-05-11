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


if __name__ == "__main__":
    convert_bin_to_csv('1970-01-01_02-46-42_data5.bin')