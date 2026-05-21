import os
import time
import threading
import subprocess
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

# ---------------- GPIO ----------------
GPIO.setmode(GPIO.BCM)
BUZZER = 18
LOCK = 23
RESET = 24

GPIO.setup(BUZZER, GPIO.OUT)
GPIO.setup(LOCK, GPIO.OUT)
GPIO.setup(RESET, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ---------------- PATHS ----------------
DATA = "data"
RFID_FILE = f"{DATA}/rfid.txt"
FACE_FILE = f"{DATA}/face.jpg"  # storing image directly
FLAG = f"{DATA}/setup_done.flag"

# ---------------- MODULES ----------------
reader = SimpleMFRC522()

# ---------------- UTILS ----------------
def buzz(on=True):
    GPIO.output(BUZZER, GPIO.HIGH if on else GPIO.LOW)

def unlock():
    GPIO.output(LOCK, GPIO.HIGH)
    time.sleep(5)
    GPIO.output(LOCK, GPIO.LOW)

def capture_face():
    """
    Capture image from PiCamera2 if available, else fswebcam.
    Returns PIL Image object.
    """
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_preview_configuration())
        cam.start()
        time.sleep(1)
        img = cam.capture_image()
        cam.close()
    except:
        img_path = "/tmp/face.jpg"
        subprocess.run(["fswebcam", "-r", "640x480", "--no-banner", img_path], check=True)
        img = Image.open(img_path)
    return img

# ---------------- RESET BUTTON ----------------
def reset_watch():
    while True:
        if GPIO.input(RESET) == GPIO.LOW:
            buzz(False)
            os.system("sudo reboot")
        time.sleep(0.2)

threading.Thread(target=reset_watch, daemon=True).start()

# ---------------- GUI ----------------
class SecurityGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")
        self.frame = tk.Frame(self.root, bg="black")
        self.frame.pack(fill="both", expand=True)
        self.video_label = None
        self.cap_img = None
        self.home_screen()

    def clear(self):
        for w in self.frame.winfo_children():
            w.destroy()

    # -------- HOME SCREEN --------
    def home_screen(self):
        self.clear()
        tk.Label(self.frame, text="SECURITY SYSTEM", fg="cyan", bg="black",
                 font=("Helvetica", 48, "bold")).pack(pady=120)
        tk.Button(self.frame, text="CONTINUE", font=("Helvetica", 36),
                  command=self.rfid_layer).pack(pady=60)

    # -------- SETUP MODE --------
    def setup_face_screen(self):
        self.clear()
        tk.Label(self.frame, text="Face Setup", font=("Helvetica", 36),
                 fg="white", bg="black").pack(pady=20)
        self.video_label = tk.Label(self.frame, bg="black")
        self.video_label.pack()
        self.root.update()
        self.start_face_capture(self.finish_setup)

    def start_face_capture(self, callback):
        """
        Shows camera feed with 3-second countdown and captures face
        """
        countdown = 3
        def count_down_step():
            nonlocal countdown
            if countdown > 0:
                self.video_label.config(text=f"Capturing in {countdown}...", font=("Helvetica", 32),
                                        fg="yellow")
                countdown -= 1
                self.root.after(1000, count_down_step)
            else:
                # Capture image
                img = capture_face()
                os.makedirs(DATA, exist_ok=True)
                img.save(FACE_FILE)
                callback()

        count_down_step()

    def finish_setup(self):
        messagebox.showinfo("Setup", "Face captured. Setup complete!")
        self.home_screen()

    # -------- RFID LAYER --------
    def rfid_layer(self):
        self.clear()
        tk.Label(self.frame, text="Tap your RFID card", font=("Helvetica", 36),
                 bg="black", fg="white").pack(pady=100)
        self.root.update()

        rfid_id, _ = reader.read()
        if os.path.exists(RFID_FILE):
            stored = open(RFID_FILE).read().strip()
        else:
            stored = str(rfid_id)
            os.makedirs(DATA, exist_ok=True)
            open(RFID_FILE, "w").write(stored)

        if str(rfid_id) != stored:
            buzz(True)
            messagebox.showerror("ACCESS DENIED", "Wrong RFID!")
            self.home_screen()
            return

        self.face_layer()

    # -------- FACE LAYER --------
    def face_layer(self):
        self.clear()
        tk.Label(self.frame, text="Face Recognition", font=("Helvetica", 36),
                 bg="black", fg="white").pack(pady=50)
        self.video_label = tk.Label(self.frame, bg="black")
        self.video_label.pack()
        self.root.update()

        countdown = 3
        def count_down_step():
            nonlocal countdown
            if countdown > 0:
                self.video_label.config(text=f"Place your face in view... {countdown}", font=("Helvetica", 24),
                                        fg="yellow")
                countdown -= 1
                self.root.after(1000, count_down_step)
            else:
                img = capture_face()
                img.save("/tmp/current_face.jpg")
                # Compare with stored image (simple pixel-wise)
                try:
                    stored_img = Image.open(FACE_FILE)
                    diff = sum(abs(a-b) for a,b in zip(img.convert("L").getdata(), stored_img.convert("L").getdata()))
                    if diff < 1000000:  # tweak threshold
                        emoji = "😊"
                    else:
                        emoji = "😐"
                except:
                    emoji = "😐"

                tk.Label(self.frame, text=emoji, font=("Helvetica", 72), fg="white", bg="black").pack(pady=50)
                self.root.update()
                time.sleep(2)
                self.pin_layer()

        count_down_step()

    # -------- PIN LAYER --------
    def pin_layer(self):
        self.clear()
        code = ['1','2','3','4']
        entered = []

        tk.Label(self.frame, text="Enter 4-digit PIN", font=("Helvetica", 32),
                 fg="white", bg="black").pack(pady=30)

        def press(d):
            entered.append(d)
            if len(entered) == 4:
                if entered == code:
                    self.access_granted()
                else:
                    buzz(True)
                    messagebox.showerror("ACCESS DENIED", "Wrong PIN")
                    self.home_screen()

        grid = tk.Frame(self.frame, bg="black")
        grid.pack()

        for i in range(1,10):
            tk.Button(grid, text=str(i), font=("Helvetica",24), width=4, height=2,
                      command=lambda x=i: press(str(x))).grid(row=(i-1)//3, column=(i-1)%3, padx=10, pady=10)
        tk.Button(grid, text='0', font=("Helvetica",24), width=4, height=2,
                  command=lambda: press('0')).grid(row=3, column=1, padx=10, pady=10)

    # -------- ACCESS GRANTED --------
    def access_granted(self):
        self.clear()
        tk.Label(self.frame, text="ACCESS GRANTED", font=("Helvetica",48,"bold"),
                 fg="lime", bg="black").pack(pady=120)
        tk.Label(self.frame, text="😄", font=("Helvetica",72), bg="black").pack()
        self.root.update()
        unlock()
        time.sleep(3)
        self.home_screen()

    def run(self):
        self.root.mainloop()


# ---------------- MAIN ----------------
if not (os.path.exists(DATA) and os.path.exists(FACE_FILE) and os.path.exists(FLAG)):
    gui = SecurityGUI()
    gui.setup_face_screen()
else:
    SecurityGUI().home_screen()
    SecurityGUI().run()
