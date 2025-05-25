import socket
import random
import subprocess
import threading
import time
import argparse
import logging
import os
import signal

def parse_arguments():
    parser = argparse.ArgumentParser(description="Simulate UDP packet loss for video streaming.")
    parser.add_argument('--listen-port', type=int, default=7000)
    parser.add_argument('--forward-port', type=int, default=7001)
    parser.add_argument('--drop-rate', type=float, default=0.05)
    parser.add_argument('--output-file', type=str, default='received.mp4')
    parser.add_argument('--input-file', type=str, default='input.mp4')
    parser.add_argument('--max-delay', type=float, default=0.0)
    parser.add_argument('--bitrate', type=str, default='1000k', help="Bitrate for FFmpeg sender (e.g., 500k, 1500k)")
    return parser.parse_args()

def check_prerequisites(input_file, listen_port, forward_port):
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("FFmpeg not found.")
        return False
    if not os.path.isfile(input_file):
        logging.error(f"Input file '{input_file}' not found.")
        return False
    return True

def start_ffmpeg_receiver(forward_port, output_file):
    cmd = [
        "ffmpeg", "-y", "-f", "mpegts",
        "-i", f"udp://127.0.0.1:{forward_port}?buffer_size=655360&timeout=5000000&reconnect=1",
        "-c:v", "mpeg2video",
        "-c:a", "mp2", "-b:a", "128k",
        "-movflags", "+faststart+frag_keyframe",
        "-fflags", "+genpts+discardcorrupt",
        output_file
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def start_ffmpeg_sender(input_file, listen_port, bitrate):
    cmd = [
        "ffmpeg", "-re", "-i", input_file,
        "-c:v", "mpeg2video", "-b:v", bitrate,
        "-c:a", "mp2", "-b:a", "128k",
        "-f", "mpegts",
        "-muxdelay", "0.05", "-muxpreload", "0.05",
        f"udp://127.0.0.1:{listen_port}?pkt_size=1316"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def log_ffmpeg_output(process, name):
    for line in iter(process.stderr.readline, ''):
        if line.strip():
            logging.debug(f"{name} FFmpeg: {line.strip()}")

def udp_packet_dropper(listen_port, forward_port, drop_rate, max_delay, stop_event):
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.bind(("0.0.0.0", listen_port))
    listen_sock.settimeout(0.5)
    forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    forward_addr = ("127.0.0.1", forward_port)
    packet_count = dropped_count = 0
    logging.info(f"Listening on UDP port {listen_port}, forwarding to {forward_port}, drop rate: {drop_rate}")
    try:
        while not stop_event.is_set():
            try:
                data, _ = listen_sock.recvfrom(65535)
                packet_count += 1
                if random.random() > drop_rate:
                    if max_delay > 0:
                        time.sleep(random.uniform(0, max_delay))
                    forward_sock.sendto(data, forward_addr)
                else:
                    dropped_count += 1
            except socket.timeout:
                continue
    finally:
        listen_sock.close()
        forward_sock.close()
        logging.info(f"Sockets closed. Total packets: {packet_count}, dropped: {dropped_count}")

def main():
    args = parse_arguments()

    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )

    if not check_prerequisites(args.input_file, args.listen_port, args.forward_port):
        return

    stop_event = threading.Event()

    ffmpeg_receiver = start_ffmpeg_receiver(args.forward_port, args.output_file)
    receiver_thread = threading.Thread(target=log_ffmpeg_output, args=(ffmpeg_receiver, "Receiver"))
    receiver_thread.start()

    dropper_thread = threading.Thread(
        target=udp_packet_dropper,
        args=(args.listen_port, args.forward_port, args.drop_rate, args.max_delay, stop_event)
    )
    dropper_thread.start()

    time.sleep(3)

    ffmpeg_sender = start_ffmpeg_sender(args.input_file, args.listen_port, args.bitrate)
    sender_thread = threading.Thread(target=log_ffmpeg_output, args=(ffmpeg_sender, "Sender"))
    sender_thread.start()

    try:
        ffmpeg_sender.wait(timeout=300)
    except subprocess.TimeoutExpired:
        logging.warning("Sender timed out.")
    except KeyboardInterrupt:
        logging.info("Interrupted.")
    finally:
        stop_event.set()
        ffmpeg_sender.send_signal(signal.SIGTERM)
        ffmpeg_receiver.send_signal(signal.SIGTERM)
        try:
            ffmpeg_sender.wait(timeout=5)
            ffmpeg_receiver.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ffmpeg_sender.kill()
            ffmpeg_receiver.kill()
        dropper_thread.join()
        receiver_thread.join()

        if os.path.isfile(args.output_file) and os.path.getsize(args.output_file) > 0:
            logging.info(f"Output saved: {args.output_file}")
        else:
            logging.error(f"No output or file is empty: {args.output_file}")

if __name__ == "__main__":
    main()
