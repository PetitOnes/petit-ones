import subprocess
import os

letter_path = "/home/cube-petit/work/embodied-claude/tmp_letter.txt"
with open(letter_path, "r") as f:
    content = f.read().strip()

result = subprocess.run(
    ["python3", "/home/cube-petit/work/embodied-claude/scripts/write_mailbox.py", "puchiteya", "puchiko", content],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print(result.stderr)

os.remove(letter_path)
os.remove(__file__)
