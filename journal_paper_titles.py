import sys
import csv
import os

def txt_to_csv(txt_file, output_path):
    with open(txt_file, 'r', encoding='utf-8', errors='replace') as infile, open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        for line in infile:
            writer.writerow([line.strip()])

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_txt_file> <output_csv_file>")
    else:
        txt_file = sys.argv[1]
        output_path = sys.argv[2]
        try:
            txt_to_csv(txt_file, output_path)
            print(f"Conversion successful. Output saved to {output_path}")
        except Exception as e:
            print(f"An error occurred: {str(e)}")