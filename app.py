#!/usr/bin/env python3

import customtkinter as ctk
from PIL import Image, ImageTk 
import subprocess
import threading
import os
import sys
import time

# -------------------------
# App configuration
# -------------------------

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_WIDTH = 850
APP_HEIGHT = 550

IDT_USB_ID = "12d1:3609"

# -------------------------
# Helper functions
# -------------------------

def detect_chipsets():
    loaders_dir = "loaders"
    if not os.path.isdir(loaders_dir):
        return []

    return sorted(
        entry for entry in os.listdir(loaders_dir)
        if os.path.isdir(os.path.join(loaders_dir, entry))
        and not entry.startswith(".")
    )


def idt_device_present():
    try:
        output = subprocess.check_output(["lsusb"], text=True)
        return IDT_USB_ID in output
    except Exception:
        return False


def have_sudo_access():
    """Check if sudo is available without password"""
    result = subprocess.run(
        ["sudo", "-n", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


# -------------------------
# GUI Application
# -------------------------

class FlasherGUI(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("PotatoNV")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(750, 500)


        ico = Image.open('icon.jpg')
        photo = ImageTk.PhotoImage(ico)
        self.wm_iconphoto(False, photo)

        self.device_connected = False
        self.sudo_password = None

        # ---- Layout ----
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---- Tabs ----
        self.tab_control = ctk.CTkTabview(self, width=APP_WIDTH - 40, height=APP_HEIGHT - 120)
        self.tab_control.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.tab_control.add("Unlock")
        self.tab_control.add("Erase FRP")

        self.tab_control.tab("Unlock").grid_columnconfigure(0, weight=1)
        self.tab_control.tab("Erase FRP").grid_columnconfigure(0, weight=1)

        # ---- Create content frames per tab ----
        self.tabs = {}
        for name in ("Unlock", "Erase FRP"):
            frame = ctk.CTkFrame(self.tab_control.tab(name))
            frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            frame.grid_columnconfigure(0, weight=1)
            self.tabs[name] = frame

        # ---- Chipset dropdown + Go button ----
        for name in ("Unlock", "Erase FRP"):
            frame = self.tabs[name]
            frame.grid_rowconfigure(3, weight=1)

            self.chipsets = detect_chipsets()
            var = ctk.StringVar(value=self.chipsets[0] if self.chipsets else "")
            setattr(self, f"{name}_chipset_var", var)

            chipset_menu = ctk.CTkOptionMenu(
                frame,
                values=self.chipsets,
                variable=var
            )
            chipset_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

            go_btn = ctk.CTkButton(
                frame,
                text="Go!",
                command=lambda tab=name: self.start_process(tab),
                height=36,
                state="disabled"
            )
            go_btn.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
            setattr(self, f"{name}_go_button", go_btn)

            console = ctk.CTkTextbox(frame, wrap="word", font=("Consolas", 12))
            console.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
            console.configure(state="disabled")
            setattr(self, f"{name}_console", console)

        # ---- Device status ----
        self.device_label = ctk.CTkLabel(
            self,
            text="📱 No Device detected\nPlease connect your device in IDT mode to begin.",
            font=ctk.CTkFont(size=14),
            justify="center",
            text_color="orange"
        )
        self.device_label.grid(row=1, column=0, pady=(0, 15))

        threading.Thread(target=self.monitor_usb, daemon=True).start()

    # -------------------------
    # USB monitoring
    # -------------------------

    def monitor_usb(self):
        while True:
            present = idt_device_present()
            if present != self.device_connected:
                self.device_connected = present
                self.after(0, self.update_device_status)
            time.sleep(1)

    def update_device_status(self):
        if self.device_connected:
            self.device_label.configure(
                text="📱 Device Detected in IDT mode",
                text_color="green"
            )
            for name in ("Unlock", "Erase FRP"):
                getattr(self, f"{name}_go_button").configure(state="normal")
        else:
            self.device_label.configure(
                text="📱 No Device detected\nPlease connect your device in IDT mode to begin.",
                text_color="orange"
            )
            for name in ("Unlock", "Erase FRP"):
                getattr(self, f"{name}_go_button").configure(state="disabled")

    # -------------------------
    # Console logging
    # -------------------------

    def log(self, tab, text):
        console = getattr(self, f"{tab}_console")
        console.configure(state="normal")
        console.insert("end", text)
        console.see("end")
        console.configure(state="disabled")

    # -------------------------
    # Sudo popup
    # -------------------------

    def request_sudo_password(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Sudo Access Required")
        popup.geometry("400x180")
        popup.resizable(False, False)

        label = ctk.CTkLabel(
            popup,
            text="Administrator privileges are required.\nPlease enter your sudo password:",
            justify="center"
        )
        label.pack(pady=15)

        entry = ctk.CTkEntry(popup, show="*", width=250)
        entry.pack(pady=10)
        entry.focus()

        error_label = ctk.CTkLabel(popup, text="", text_color="red")
        error_label.pack()

        def submit():
            pwd = entry.get()
            if not pwd:
                return
            test = subprocess.run(
                ["sudo", "-S", "true"],
                input=pwd + "\n",
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if test.returncode == 0:
                self.sudo_password = pwd
                popup.destroy()
            else:
                error_label.configure(text="Incorrect password")

        button = ctk.CTkButton(popup, text="Authenticate", command=submit)
        button.pack(pady=10)

        popup.update_idletasks()
        popup.after(10, popup.grab_set)
        self.wait_window(popup)
        return self.sudo_password is not None

    # -------------------------
    # Process handling
    # -------------------------

    def start_process(self, tab):
        if not have_sudo_access() and not self.sudo_password:
            if not self.request_sudo_password():
                self.log(tab, "[ERROR] Sudo authentication failed\n")
                return

        chipset = getattr(self, f"{tab}_chipset_var").get()
        console = getattr(self, f"{tab}_console")
        console.configure(state="normal")
        console.delete("1.0", "end")
        console.configure(state="disabled")

        getattr(self, f"{tab}_go_button").configure(state="disabled")

        threading.Thread(
            target=self.run_main_script,
            args=(tab, chipset),
            daemon=True
        ).start()

    def run_main_script(self, tab, chipset):
        arg = "--unlock" if tab == "Unlock" else "--wipefrp"
        cmd = [
            "sudo",
            "-S",
            sys.executable,
            "main.py",
            "--chipset",
            chipset,
            arg
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        if self.sudo_password:
            process.stdin.write(self.sudo_password + "\n")
            process.stdin.flush()

        for line in process.stdout:
            self.log(tab, line)

        process.wait()
        self.log(tab, "\n[*] Process finished.\n")

        if self.device_connected:
            getattr(self, f"{tab}_go_button").configure(state="normal")


# -------------------------
# Entry point
# -------------------------

if __name__ == "__main__":
    app = FlasherGUI()
    app.mainloop()
