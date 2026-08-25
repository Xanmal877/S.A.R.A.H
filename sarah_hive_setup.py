"""
One-time local setup for hive networking (modules/hive/).

Usage:
    python3 sarah_hive_setup.py init-secret [--force]
        Generates ~/.sarah/hive_secret (chmod 600) and prints it. Copy this
        exact file to every other machine you want in the same hive
        (scp/USB/etc.) - it is never transmitted over the network itself.

    python3 sarah_hive_setup.py show-config
        Prints the current ~/.sarah/hive_config.json (or the defaults that
        would be used if it doesn't exist yet). Edit that file directly to
        set "role": "core" on the node that should poll/aggregate peers
        (e.g. the Pi), and to change the port or poll_interval.
"""
import json
import sys

from modules.hive.config import init_secret, load_config, CONFIG_PATH, SECRET_PATH


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "init-secret":
        force = "--force" in sys.argv
        key = init_secret(force=force)
        print(f"Hive secret written to {SECRET_PATH} (chmod 600).")
        print("Copy this file to every other machine joining the hive:")
        print(key)
    elif cmd == "show-config":
        print(f"(from {CONFIG_PATH} if present, else defaults)")
        print(json.dumps(load_config(), indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
