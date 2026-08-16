#!/usr/bin/env python3
"""
Compile bareiron from source.
"""

import os
import sys
import subprocess


def main():
    # ---- Check for generated registries header ----
    if not (os.path.isfile("./include/registries.h") and os.path.isfile("./src/registries.c")):
        print("Error: 'include/registries.h' or/and 'src/registries.c' is missing.")
        print("Please run 'python extract_registries.py' to generate it.")
        sys.exit(1)

    # ---- Compile ----
    if sys.platform == "win32":
        subprocess.run("gcc ./src/*.c -O2 -I./include/ -o bareiron -static -lws2_32 -pthread", check=True)
    else:
        subprocess.run("gcc ./src/*.c -O2 -I./include/ -o bareiron", check=True)

if __name__ == "__main__":
    main()
