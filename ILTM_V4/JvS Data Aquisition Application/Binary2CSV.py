import struct
import csv
import os

def convert_bin_to_csv(bin_filename):
    # Define the binary format: 
    # I = unsigned int (4 bytes) - timestamp_ms
    # H = unsigned short (2 bytes) - id
    # f = float (4 bytes) - value
    # '<' ensures little-endian (standard for ESP32)
    entry_format = '<IHf'
    entry_size = struct.calcsize(entry_format)
    
    csv_filename = bin_filename.replace('.bin', '.csv')
    
    if not os.path.exists(bin_filename):
        print(f"Error: {bin_filename} not found.")
        return

    print(f"Converting {bin_filename} to {csv_filename}...")

    with open(bin_filename, 'rb') as bin_file, open(csv_filename, 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        # Write the header
        writer.writerow(['timestamp_ms', 'id', 'value'])
        
        while True:
            chunk = bin_file.read(entry_size)
            if not chunk or len(chunk) < entry_size:
                break
            
            # Unpack the 10-byte binary chunk into Python variables
            timestamp_ms, sensor_id, value = struct.unpack(entry_format, chunk)
            
            # Write to CSV
            writer.writerow([timestamp_ms, sensor_id, f"{value:.4f}"])

    print("Done!")

# Usage
if __name__ == "__main__":
    # Change this to match your file name from the SD card
    convert_bin_to_csv('1946-12-14_05-43-56_data163.bin')