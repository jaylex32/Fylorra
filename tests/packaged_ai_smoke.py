import os
import subprocess
import sys
from pathlib import Path


def run_action(binary: Path, action: str) -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["FYLORRA_SMOKE_AI_DOWNLOAD"] = "1"
    env["FYLORRA_SMOKE_AI_DOWNLOAD_FAKE"] = "1"
    env["FYLORRA_SMOKE_AI_ACTION"] = action
    proc = subprocess.run(
        [str(binary)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(f"Packaged AI smoke failed for {action}: exit {proc.returncode}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: packaged_ai_smoke.py <binary>", file=sys.stderr)
        return 2
    binary = Path(sys.argv[1])
    if not binary.exists():
        print(f"Binary not found: {binary}", file=sys.stderr)
        return 2
    run_action(binary, "download")
    run_action(binary, "load_unload")
    print("Packaged AI smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())