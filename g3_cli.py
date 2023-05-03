#!/usr/bin/env python3

import logging
import argparse
import threading
import signal

import serial

import g3_comms.g3_rx

default_port="/dev/ttyACM0"

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    g3_comms.g3_rx.G3Rx.quit()

def main():
    logging.debug("*** Starting cli")

    port = args.port
    logging.info(f'Using port {port}')

    signal.signal(signal.SIGINT, shutdown_handler)

    device = serial.Serial(port, baudrate=115200, timeout=0)
    logging.info(f"Opened serial port {device.name}")

    rx_protocol = g3_comms.g3_rx.G3Rx(device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    rx_thread.join()

if __name__ == "__main__":
    main()
