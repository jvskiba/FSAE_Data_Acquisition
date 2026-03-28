import struct
import csv
import pandas as pd

# Struct format:
# <  = little endian (ESP32 is little endian)
# I  = uint32_t
# B  = uint8_t
# f  = float
STRUCT_FORMAT = "<IBf"
ENTRY_SIZE = struct.calcsize(STRUCT_FORMAT)

def convert_bin_to_csv(input_file, output_file):
    with open(input_file, "rb") as f, open(output_file, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        
        # Header
        writer.writerow(["timestamp", "id", "value"])
        
        while True:
            chunk = f.read(ENTRY_SIZE)
            if len(chunk) < ENTRY_SIZE:
                break
            
            timestamp, id_, value = struct.unpack(STRUCT_FORMAT, chunk)
            writer.writerow([timestamp, id_, value])

    print(f"Converted {input_file} → {output_file}")

import pandas as pd

def convert_to_dataframe(input_file):
    data = []

    with open(input_file, "rb") as f:
        while True:
            chunk = f.read(ENTRY_SIZE)
            if len(chunk) < ENTRY_SIZE:
                break
            data.append(struct.unpack(STRUCT_FORMAT, chunk))

    df = pd.DataFrame(data, columns=["timestamp", "id", "value"])
    return df

INPUT_FILE = "33658-09-27_01-30-02_data50.bin"
OUTPUT_FILE = "log.csv"

if __name__ == "__main__":
    convert_bin_to_csv(INPUT_FILE, OUTPUT_FILE)
    
    df = convert_to_dataframe(INPUT_FILE)
    print(df.head())
    #df.to_csv("log.csv", index=False)