from pathlib import Path
import subprocess
import sys

backup = Path("storage/backups/database/ecommerce_chatbot_before_migration.dump")

if not backup.exists() or backup.stat().st_size == 0:
    print("ERROR: Backup file is missing or empty.")
    sys.exit(1)

result = subprocess.run(
    [
        "docker", "exec", "-i", "ecommerce-postgres",
        "pg_restore", "--list", "-"
    ],
    input=backup.read_bytes(),
    capture_output=True,
)

if result.returncode != 0:
    print(result.stderr.decode("utf-8", errors="replace"))
    sys.exit(result.returncode)

print("Backup archive is readable.")
print(result.stdout.decode("utf-8", errors="replace")[:1500])
