import subprocess
import os
import csv
import time
import cv2
import numpy as np
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

def calculate_psnr_ssim(input_path, output_path, max_frames=300):
    cap1 = cv2.VideoCapture(input_path)
    cap2 = cv2.VideoCapture(output_path)

    if not cap1.isOpened() or not cap2.isOpened():
        print(" Không mở được file video.")
        return "ERROR", "ERROR"

    psnr_list = []
    ssim_list = []
    frame_count = 0

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            break

        if frame1.shape != frame2.shape:
            frame2 = cv2.resize(frame2, (frame1.shape[1], frame1.shape[0]))

        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        psnr_val = psnr(gray1, gray2, data_range=255)
        ssim_val = ssim(gray1, gray2, data_range=255)

        psnr_list.append(psnr_val)
        ssim_list.append(ssim_val)

        frame_count += 1
        if frame_count >= max_frames:
            break

    cap1.release()
    cap2.release()

    if len(psnr_list) == 0:
        return "N/A", "N/A"

    avg_psnr = round(np.mean(psnr_list), 3)
    avg_ssim = round(np.mean(ssim_list), 4)

    return avg_psnr, avg_ssim

bitrates = ["500k", "1000k", "1500k", "2000"]
discard_rates = [0.0, 0.05]
input_video = "input_mpegts.ts"

results_dir = "results"
os.makedirs(results_dir, exist_ok=True)
summary_path = os.path.join(results_dir, "summary.csv")

with open(summary_path, mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Bitrate", "DiscardRate", "PSNR", "SSIM", "OutputVideo"])

    for bitrate in bitrates:
        for discard_rate in discard_rates:
            tag = f"{bitrate}_{int(discard_rate * 100)}"
            output_file = os.path.join(results_dir, f"received_{tag}.ts")

            print(f"\n Running test with bitrate={bitrate}, drop={discard_rate}...")

    
            cmd = [
                "python", "udp_packet.py",
                "--input-file", input_video,
                "--output-file", output_file,
                "--drop-rate", str(discard_rate),
                "--bitrate", bitrate
            ]
            result = subprocess.run(cmd)

            if result.returncode != 0 or not os.path.exists(output_file):
                print(f" Failed to generate output video for {tag}")
                writer.writerow([bitrate, discard_rate, "ERROR", "ERROR", output_file])
                continue

            time.sleep(1)

            psnr_val, ssim_val = calculate_psnr_ssim(input_video, output_file)
            print(f" Done {tag}: PSNR={psnr_val}, SSIM={ssim_val}")

            writer.writerow([bitrate, discard_rate, psnr_val, ssim_val, output_file])
