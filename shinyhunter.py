import nxbt
from nxbt import Buttons
import subprocess
import numpy as np
import cv2
import time
import os
from dotenv import load_dotenv
import requests
from time import sleep
from threading import Thread, Event

shutdown_event = Event()
DEBUG = False  # Toggle to True if you want OpenCV windows
load_dotenv()

# add BotFather and Get My ID here if you want telegram notifications
CHAT_ID = os.getenv('CHAT_ID')
BOT_TOKEN = os.getenv('BOT_TOKEN')
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Stream and frame setup
STREAM_URL = 'rtmp://192.168.0.249/live/stream' # set your rtmp server ip
WIDTH, HEIGHT = 640, 360
FRAME_SIZE = WIDTH * HEIGHT * 3  # for bgr24

# VALUES FOR DIALGA
# SHINY_LOWER = np.array([80, 120, 80])
# SHINY_UPPER = np.array([95, 255, 160])

# Shiny HSV range: ARCEUS
SHINY_LOWER = np.array([27, 91, 244])
SHINY_UPPER = np.array([35, 113, 255])

TRIGGER_PIXEL_COUNT = 25000
reset_counter = 0

# Macros
open_game = """A 0.1s\n0.1s"""
title = """A 0.1s\n12.0s\nA 0.1s\n3.0s\nA 0.1s\n9.0s"""
encounter = """DPAD_UP 1.0s\n15.0s\nA 0.1s\n0.1s\nA 0.1s"""
close_game = """HOME 0.1s\n0.5s\nX 0.1s\n0.1s\nA 0.1s\n0.1s"""

# ----------------------------
# Color Detection Thread
# ----------------------------
def color_detector():
    # ffmpeg_cmd = [
    #     'ffmpeg',
    #     '-fflags', 'nobuffer',
    #     '-flags', 'low_delay',
    #     '-framedrop',
    #     '-flush_packets', '1',
    #     '-i', STREAM_URL,
    #     '-loglevel', 'quiet',
    #     '-f', 'rawvideo',
    #     '-pix_fmt', 'bgr24',
    #     '-vf', f'scale={WIDTH}:{HEIGHT}',
    #     '-'
    # ]

    ffmpeg_cmd = [
        'ffmpeg',
        '-i', STREAM_URL,
        '-loglevel', 'quiet',               # suppress ffmpeg output
        '-f', 'rawvideo',
        '-pix_fmt', 'bgr24',
        '-vf', f'scale={WIDTH}:{HEIGHT}',             # downscale for speed
        '-'
    ]

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE
    )
    print("Watching stream for shiny...")

    try:
        frame_num = 0
        while not shutdown_event.is_set():
            raw_frame = process.stdout.read(FRAME_SIZE)
            if len(raw_frame) != FRAME_SIZE:
                print("Frame incomplete or stream error.")
                break
            frame_num += 1

            frame = np.frombuffer(raw_frame, np.uint8).reshape((HEIGHT, WIDTH, 3))
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, SHINY_LOWER, SHINY_UPPER)
            shiny_pixel_count = cv2.countNonZero(mask)

            if DEBUG:
                cv2.imshow('frame', frame)
                cv2.imshow('mask', mask)
                cv2.waitKey(1)

            print(f"Frame: {frame_num} | Matching pixels: {shiny_pixel_count}".ljust(60), end='\r')

            if shiny_pixel_count > TRIGGER_PIXEL_COUNT:
                print("\nSHINY FOUND!")
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                message = {
                    "chat_id": CHAT_ID,
                    "text":  f"SHINY FOUND {timestamp} @ {reset_counter} resets"
                }
                requests.post(TELEGRAM_URL, data=message)
                cv2.imwrite(f'shiny_{timestamp}.png', frame)
                shutdown_event.set()
                break

    finally:
        process.kill()
        if DEBUG:
            cv2.destroyAllWindows()

def controller_automation(nx, controller_idx):
    global reset_counter
    nx.press_buttons(controller_idx, [Buttons.A])
    sleep(1)
    nx.press_buttons(controller_idx, [Buttons.HOME])
    sleep(1)

    while not shutdown_event.is_set():
        nx.macro(controller_idx, open_game)
        sleep(1)
        nx.macro(controller_idx, title)
        sleep(1)
        nx.macro(controller_idx, encounter)
        sleep(16)  # Encounter time
        if shutdown_event.is_set():
            break
        nx.macro(controller_idx, close_game)
        reset_counter += 1

# ----------------------------
# Main Runner
# ----------------------------
if __name__ == "__main__":
    print("Starting NXBT controller automation")
    os.system("bluetoothctl power on")
    os.system("bluetoothctl discoverable on")
    sleep(1)
    nx = nxbt.Nxbt()

    adapters = nx.get_available_adapters()
    if not adapters:
        print("No Bluetooth adapters found!")
        exit()

    controller_idx = nx.create_controller(nxbt.PRO_CONTROLLER, adapter_path=adapters[-1])
    nx.wait_for_connection(controller_idx)
    print("Controller connected!")
    
    controller = Thread(target=controller_automation, args=(nx, controller_idx))
    detector = Thread(target=color_detector)
    
    detector.start()
    controller.start()
    
    controller.join()
    detector.join()

    print("Program exiting.")
    exit()
