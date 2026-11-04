from pathlib import Path
import subprocess
import sys

backup_dir = Path("storage/backups")
backup_dir.mkdir(parents=True, exist_ok=True)
backup_file = backup_dir / "ecommerce_chatbot_before_email_verification.dump"

cmd = [
    "docker", "exec", "ecommerce-postgres",
    "pg_dump", "-U", "chatbot_user",
    "-d", "ecommerce_chatbot", "-F", "c",
    "--no-owner", "--no-privileges",
]

try:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="replace"))
        sys.exit(result.returncode)

    if not result.stdout:
        print("Backup was empty; no file written.")
        sys.exit(1)

    backup_file.write_bytes(result.stdout)
    print(f"Backup saved: {backup_file}")
    print(f"Backup size: {backup_file.stat().st_size:,} bytes")
except FileNotFoundError:
    print("Docker command was not found.")
    sys.exit(1)
