#!/usr/bin/env python3
"""
Extract Minecraft server registries and generate C source files.
"""

import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

REQUIRED_MAJOR = 21
SERVER_JAR = os.environ.get("SERVER_JAR", "server.jar")
NOTCHIAN_DIR = os.path.join(SCRIPT_DIR, "notchian")


def check_java():
    """Verify that Java 21+ is available."""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True
        )
    except FileNotFoundError:
        print("Java not found in PATH.")
        sys.exit(1)

    # java -version prints to stderr
    output = result.stderr or result.stdout
    match = re.search(r'version "(\d+)', output)
    if not match:
        print(f"Could not determine Java version from: {output.strip()}")
        sys.exit(1)

    major = int(match.group(1))
    if major < REQUIRED_MAJOR:
        print(f"Java {REQUIRED_MAJOR} or newer required, but found Java {major}.")
        sys.exit(1)

    print(f"Java {major} detected.")


def prepare_notchian_dir():
    """Create the notchian working directory if needed and return its path."""
    if not os.path.isdir(NOTCHIAN_DIR):
        print(f"Creating {NOTCHIAN_DIR} directory...")
        os.makedirs(NOTCHIAN_DIR)
    return NOTCHIAN_DIR


def dump_registries(notchian_dir):
    """Run the Minecraft server's data generator to dump registries."""
    jar_path = os.path.join(notchian_dir, SERVER_JAR)
    if not os.path.isfile(jar_path):
        print(f"No server.jar found (looked for {jar_path}).")
        print(f'Please run "python download_server.py" to download it,')
        print('or download the server.jar manually and place it in the "notchian" directory.')
        sys.exit(1)

    print("Dumping registries via Minecraft data generator...")
    subprocess.run(
        ["java", "-DbundlerMainClass=net.minecraft.data.Main", "-jar", SERVER_JAR, "--reports", "--server"],
        cwd=notchian_dir,
        check=True,
    )


def main():
    check_java()
    notchian_dir = prepare_notchian_dir()
    dump_registries(notchian_dir)
    print("Registry dump complete.")


if __name__ == "__main__":
    main()
