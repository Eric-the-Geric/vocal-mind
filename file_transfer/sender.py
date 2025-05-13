# sender.py
import socket
import os
import sys
import tqdm

if len(sys.argv) != 2:
    print("Usage: python sender.py <filename>")
    sys.exit(1)

filename = sys.argv[1]
if not os.path.isfile(filename):
    print(f"[!] File not found: {filename}")
    sys.exit(1)

SERVER_HOST = os.getenv("SERVER_HOST")
  # Replace with your server's IP
SERVER_PORT = 5000
BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"

filesize = os.path.getsize(filename)
s = socket.socket()
s.connect((SERVER_HOST, SERVER_PORT))

# Send file header
s.send(f"{os.path.basename(filename)}{SEPARATOR}{filesize}".encode())

# Send file data
progress = tqdm.tqdm(range(filesize), f"Sending {filename}", unit="B", unit_scale=True, unit_divisor=1024)
with open(filename, "rb") as f:
    while True:
        bytes_read = f.read(BUFFER_SIZE)
        if not bytes_read:
            break
        s.sendall(bytes_read)
        progress.update(len(bytes_read))

s.close()
print("[*] File sent.")
