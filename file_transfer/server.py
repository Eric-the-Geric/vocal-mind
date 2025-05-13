# server.py
import socket
import tqdm
import os

SERVER_HOST = "0.0.0.0"  # Listen on all interfaces
SERVER_PORT = 5000
BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
SAVE_DIR = "received_files"

# Create the save directory if it doesn't exist
os.makedirs(SAVE_DIR, exist_ok=True)

s = socket.socket()
s.bind((SERVER_HOST, SERVER_PORT))
s.listen(5)
print(f"[*] Listening as {SERVER_HOST}:{SERVER_PORT}")

while True:
    client_socket, address = s.accept()
    print(f"[+] Connected by {address}")

    try:
        received = client_socket.recv(BUFFER_SIZE).decode()
        if not received:
            print("[!] Empty header. Skipping.")
            client_socket.close()
            continue

        if received.strip().lower() == "exit":
            client_socket.close()
            continue

        filename, filesize = received.split(SEPARATOR)
        filename = os.path.basename(filename)
        filesize = int(filesize)
        save_path = os.path.join(SAVE_DIR, filename)

        progress = tqdm.tqdm(range(filesize), f"Receiving {filename}", unit="B", unit_scale=True, unit_divisor=1024)
        with open(save_path, "wb") as f:
            bytes_received = 0
            while bytes_received < filesize:
                chunk = client_socket.recv(min(BUFFER_SIZE, filesize - bytes_received))
                if not chunk:
                    break
                f.write(chunk)
                bytes_received += len(chunk)
                progress.update(len(chunk))

        print(f"[+] Saved file to {save_path}")
        client_socket.close()

    except Exception as e:
        print(f"[!] Error: {e}")
        client_socket.close()
