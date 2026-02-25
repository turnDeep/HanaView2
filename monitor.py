import time
import sys

log_file = 'rs_full_log.txt'
print(f"Monitoring {log_file}...")

while True:
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            if "Scan complete" in content:
                print("Scan complete detected!")
                break
            # print last line
            lines = content.strip().split('\n')
            if lines:
                print(f"Last line: {lines[-1][:100]}")
    except FileNotFoundError:
        pass

    time.sleep(10)
