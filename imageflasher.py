import binascii
import itertools
import serial
import serial.tools.list_ports
import os
import time
import platform
from log import log_info, log_warning, log_error  # Import your custom log functions

# Constants
TOOLNAME = "imageflasher"
BOOT_HEAD_LEN = 0x4F00
MAX_DATA_LEN = 0x400
IDT_BAUDRATE = 115200
IDT_VID = 0x12D1
IDT_PID = 0x3609
UPLOAD_TIMEOUT = 50  # Seconds

# CRC Calculation
def calc_crc(data, crc=0):
    for char in data:
        crc = ((crc << 8) | char) ^ binascii.crc_hqx(bytes([(crc >> 8) & 0xFF]), 0)
    for _ in range(2):
        crc = ((crc << 8) | 0) ^ binascii.crc_hqx(bytes([(crc >> 8) & 0xFF]), 0)
    return crc & 0xFFFF

# Exception classes
class FlashException(Exception):
    pass

class DeviceDetectException(Exception):
    pass

class TimeoutException(Exception):
    pass

# Protocol frames
startframe = bytes([0xFE, 0x00, 0xFF, 0x01, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x02, 0x01])
headframe = startframe[:4]
dataframe = bytes([0xDA])
tailframe = bytes([0xED])
ack = bytes([0xAA])

class ImageFlasher:
    def __init__(self):
        self.startframe = startframe
        self.headframe = headframe
        self.dataframe = dataframe
        self.tailframe = tailframe
        self.ack = ack
        self.serial = None

    def send_frame(self, data, loop):
        crc = calc_crc(data)
        data += crc.to_bytes(2, byteorder="big", signed=False)
        fails = []
        for _ in itertools.repeat(None, loop - 1):
            try:
                if self.serial:
                    self.serial.reset_output_buffer()
                    self.serial.reset_input_buffer()
                    self.serial.write(data)
                    ack = self.serial.read(1)
                else:
                    ack = self.ack
                return
            except Exception as e:
                fails.append(e)
        for ex in fails:
            raise ex

    def send_start_frame(self):
        if self.serial:
            self.serial.timeout = 0.03
        log_info("Sending start frame", TOOLNAME)
        self.send_frame(self.startframe, 10000)

    def send_head_frame(self, length, address):
        if self.serial:
            self.serial.timeout = 0.09
        log_info("Sending header frame", TOOLNAME)
        data = self.headframe
        data += length.to_bytes(4, byteorder="big", signed=False)
        data += address.to_bytes(4, byteorder="big", signed=False)
        self.send_frame(data, 10)

    def send_data_frame(self, n, data):
        if self.serial:
            self.serial.timeout = 0.45
        head = bytearray(self.dataframe)
        head.append(n & 0xFF)
        head.append((~n) & 0xFF)
        self.send_frame(bytes(head) + data, 40)

    def send_tail_frame(self, n):
        if self.serial:
            self.serial.timeout = 0.01
        log_info("Sending tail frame", TOOLNAME)
        data = bytearray(self.tailframe)
        data.append(n & 0xFF)
        data.append((~n) & 0xFF)
        self.send_frame(bytes(data), 10)

    def send_data(self, data, length, address):
        if isinstance(data, bytes):
            length = len(data)
        if length == 0 or not isinstance(length, int):
            raise FlashException("Invalid data length")

        nframes = length // MAX_DATA_LEN + (1 if length % MAX_DATA_LEN > 0 else 0)
        self.send_head_frame(length, address)

        start_time = time.time()
        last_percent = -1

        for n in range(nframes):
            if time.time() - start_time > UPLOAD_TIMEOUT:
                raise TimeoutException("Upload timeout exceeded!")

            chunk = data[n * MAX_DATA_LEN: (n + 1) * MAX_DATA_LEN] if isinstance(data, bytes) else data.read(MAX_DATA_LEN)
            self.send_data_frame(n + 1, chunk)

            percent = (100 * (n + 1)) // nframes
            if percent > last_percent:
                print(f"\rUploading... {percent}% complete", end="", flush=True)
                last_percent = percent

        print("\nUpload complete!")
        self.send_tail_frame(n + 1)
        time.sleep(0.5)

    def download_from_disk(self, fil, address):
        with open(fil, "rb") as f:
            self.send_data(f, os.stat(fil).st_size, address)

    def connect_serial(self, device=None):
        if device is None:
            ports = serial.tools.list_ports.comports(include_links=False)
            matching_ports = [p for p in ports if p.vid == IDT_VID and p.pid == IDT_PID]
            if not matching_ports:
                raise DeviceDetectException("No IDT mode device found")
            if len(matching_ports) > 1:
                raise DeviceDetectException("Multiple IDT devices found. Specify manually.")
            device = matching_ports[0].device
            log_warning(f"Autoselecting {device}", TOOLNAME)

        # Cross-platform fix
        if platform.system() == "Windows" and device.upper().startswith("COM"):
            port = device.replace("COM", r"\\.\COM")
        else:
            port = device

        self.serial = serial.Serial(
            port=port,
            baudrate=IDT_BAUDRATE,
            timeout=1,
            dsrdtr=True,
            rtscts=True
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.serial:
            self.serial.close()

    def xupload(self, address, data, length):
        if not self.serial:
            raise FlashException("Serial port not connected")

        if isinstance(data, bytes):
            length = len(data)
        if length == 0:
            raise FlashException("No data to upload")

        nframes = length // MAX_DATA_LEN + (1 if length % MAX_DATA_LEN > 0 else 0)

        # Start upload
        self.send_head_frame(length, address)

        offset = 0
        for seq in range(1, nframes + 1):
            chunk = data[offset:offset + MAX_DATA_LEN]
            self.send_data_frame(seq, chunk)
            offset += MAX_DATA_LEN
            print(f"{min(offset, length)} / {length} bytes", end="\r")

        # Finish upload
        self.send_tail_frame(nframes)
        print(f"{length} / {length} bytes\nUpload complete!")
        time.sleep(0.1)

# Wrapper function for external usage
def download(address, filename, partition=""):
    try:
        with ImageFlasher() as flasher:
            flasher.connect_serial()
            flasher.send_start_frame()
            flasher.download_from_disk(filename, address)
            log_info(f"Flashing {partition if partition else 'image'} completed successfully!", TOOLNAME)
    except Exception as e:
        log_error(f"Flashing failed: {str(e)}", TOOLNAME)
