#!/usr/bin/env python3
# Script for R0rt1z2, made by Kethily :)

import time
import os
import re
import random
import string
import hashlib
import argparse
import xml.etree.ElementTree as ET

from imageflasher import ImageFlasher


def load_manifest(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    roles = {}
    for image in root.findall("image"):
        role = image.get("role")
        addr = image.get("address")
        if role and addr:
            roles[role] = int(addr, 0)
    return roles


def run_fastboot(cmd):
    print(f"[FASTBOOT] {cmd}")
    return os.popen(f"fastboot {cmd} 2>&1").read()


def generate_unlock_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(16))


def sha256_bytes(s):
    return hashlib.sha256(s.encode("ascii")).digest()



def main(chipset, unlock, wipefrp):
    if unlock and wipefrp:
        raise RuntimeError("Cannot use --unlock and --wipefrp at the same time")

    loaders_dir = f"loaders/{chipset}"
    manifest_path = f"{loaders_dir}/manifest.xml"

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")


    roles = load_manifest(manifest_path)

    print(f"[INFO] Uploading images for chipset: {chipset}")

    for role in ("xloader", "fastboot", "uce"):
        if role in roles:
            print(f"[DEBUG] {role} address: 0x{roles[role]:08X}")

    # ---- Stage 0: Upload images ----
    with ImageFlasher() as flasher:
        flasher.connect_serial()

        print("[INFO] Uploading xloader...")
        flasher.xupload(
            roles["xloader"],
            open(f"{loaders_dir}/xloader.img", "rb").read(),
            os.path.getsize(f"{loaders_dir}/xloader.img")
        )

        if "uce" in roles:
            print("[INFO] Uploading uce...")
            flasher.xupload(
                roles["uce"],
                open(f"{loaders_dir}/uce.img", "rb").read(),
                os.path.getsize(f"{loaders_dir}/uce.img")
            )

        print("[INFO] Uploading fastboot...")
        flasher.xupload(
            roles["fastboot"],
            open(f"{loaders_dir}/fastboot.img", "rb").read(),
            os.path.getsize(f"{loaders_dir}/fastboot.img")
        )

    print("[INFO] Upload complete, waiting 5 seconds.")
    time.sleep(5)

    if wipefrp:
        # ---- Stage 1: Wipe FRP ----
        print("[INFO] Wiping FRP data...")

        run_fastboot("oem frp-erase")

        print("[INFO] Done.")
        return

    if unlock:
        # ---- Stage 1: Read stock key ----
        output = run_fastboot("getvar:nve:WVLOCK")
        match = re.search(r"([A-Z0-9]{16})", output)

        if match:
            stockkey = match.group(1)
            print("[INFO] Stock key:", stockkey)
            with open("stock_key.txt", "w") as f:
                f.write(stockkey + "\n")
        else:
            print("[INFO] No stock key found.")
            stockkey = None

        # ---- Stage 2: Generate + set new key ----
        newkey = generate_unlock_code()
        print("[INFO] New unlock key:", newkey)

        with open("new_key.txt", "w") as f:
            f.write(newkey + "\n")

        run_fastboot(f"getvar:nve:WVLOCK@{newkey}")

        usrkey = sha256_bytes(newkey).hex()
        run_fastboot(f"getvar:nve:USRKEY@{usrkey}")

        run_fastboot("getvar:nve:FBLOCK@00")

        print("[INFO] Done.")
        print("[INFO] Old key saved to stock_key.txt")
        print("[INFO] New key saved to new_key.txt")
        print("[INFO] Thanks for using my script :)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PotatoNV for Huawei Hisilicon devices")

    parser.add_argument(
        "--chipset",
        required=True,
        help="Chipset name (e.g. hisi960)"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--unlock", action="store_true", help="Read bootloader unlock code")
    mode.add_argument("--wipefrp", action="store_true", help="Erase FRP + userdata + metadata")

    args = parser.parse_args()
    main(args.chipset, args.unlock, args.wipefrp)
