#!/usr/bin/env python3
"""
Download Minecraft server.jar via the official version manifest.
"""

import hashlib
import json
import os
import sys
import urllib.request

# ============================================================
# Default Minecraft version to download (change as needed)
# ============================================================
DEFAULT_VERSION = "1.21.8"

VERSION_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

# Where to save the jar (relative to this script's directory)
NOTCHIAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notchian")


def fetch_json(url):
    """Fetch and parse JSON from a URL."""
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    return json.loads(data)


def download_file(url, dest_path, sha1=None):
    """Download a file with a simple progress indicator."""
    print(f"  Downloading from: {url}")
    with urllib.request.urlopen(url) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        hasher = hashlib.sha1()
        chunk_size = 64 * 1024
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    sys.stdout.write(f"\r  {downloaded // 1024} KiB / {total // 1024} KiB ({pct}%)")
                    sys.stdout.flush()
        print()
    if sha1 is not None:
        actual = hasher.hexdigest()
        if actual != sha1:
            print(f"  SHA1 mismatch! Expected {sha1}, got {actual}", file=sys.stderr)
            return False
        print(f"  SHA1 verified: {actual}")
    return True


def main():
    version = DEFAULT_VERSION
    if len(sys.argv) > 1:
        version = sys.argv[1]

    print(f"Minecraft server.jar downloader")
    print(f"  Target version: {version}")

    # Step 1: Fetch the version manifest
    print("Fetching version manifest...")
    manifest = fetch_json(VERSION_MANIFEST_URL)

    # Step 2: Find the version entry
    version_entry = None
    for v in manifest.get("versions", []):
        if v["id"] == version:
            version_entry = v
            break

    if version_entry is None:
        print(f"Error: version '{version}' not found in manifest.", file=sys.stderr)
        available = [v["id"] for v in manifest.get("versions", [])[:10]]
        print(f"Some available versions: {', '.join(available)} ...", file=sys.stderr)
        sys.exit(1)

    print(f"  Found version entry: {version_entry['type']}")

    # Step 3: Fetch the per-version metadata
    print("Fetching version metadata...")
    version_meta = fetch_json(version_entry["url"])

    server_info = version_meta.get("downloads", {}).get("server")
    if server_info is None:
        print(f"Error: no server download available for version '{version}'.", file=sys.stderr)
        sys.exit(1)

    # Step 4: Prepare output directory
    os.makedirs(NOTCHIAN_DIR, exist_ok=True)
    jar_path = os.path.join(NOTCHIAN_DIR, "server.jar")

    # Step 5: Download
    print(f"Downloading server.jar ({server_info['size'] // 1024} KiB)...")
    if not download_file(server_info["url"], jar_path, server_info.get("sha1")):
        sys.exit(1)

    print(f"Done. server.jar saved to: {jar_path}")


if __name__ == "__main__":
    main()
