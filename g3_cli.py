#!/usr/bin/env python3

import logging
import argparse
import struct

import serial

default_port="/dev/ttyACM0"

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

G3_HEADER_LEN = 8 # Not including sync bytes
G3_TAG_LEN = 8
G3_CRC_LEN = 2

def syncMsg(device):
    logging.debug("syncMsg")
    one = device.read(1)
    while True:
        while one.hex() != '16':
            one = device.read(1)
        logging.debug('got first sync')
        two = device.read(1)
        if two.hex() == '16':
            logging.debug('got second sync')
            break
        logging.debug('not second, resync')

def getMsg(device):
    logging.debug("getMsg")
    syncMsg(device)

    msg = {}
    header = device.read(G3_HEADER_LEN)
    if len(header) != G3_HEADER_LEN:
        logging.error(f"Invalid header: {header.hex(' ')}")
        return msg

    up_header = struct.unpack("<BHBI", header)
    msg['cmd'] = up_header[0]
    msg['size'] = up_header[1]
    msg['sec_mode'] = up_header[2]
    msg['counter'] = up_header[3]

    msg['data'] = device.read(msg['size'])
    data_len = len(msg['data'])
    if data_len < msg['size']:
        logging.error(f"Short data. {data_len} of msg['size']")

    if msg['sec_mode'] > 0:
        check_len = G3_TAG_LEN + G3_CRC_LEN
    else:
        check_len = G3_CRC_LEN
    check = device.read(check_len)
    if len(check) < check_len:
        logging.error("Invalid check length")
    if msg['sec_mode'] > 0:
        up_check = struct.unpack("<QH", check)
        msg['sec_tag'] = up_check[0]
        msg['crc'] = up_check[1]
    else:
        up_check = struct.unpack("<H", check)
        msg['crc'] = up_check[0]
        msg['sec_tag'] = 0

    # TODO: check the CRC

    return msg

def decodeMsg(msg):
    logging.info(f"decodeMsg: {msg}")

def main():
    logging.debug("*** Starting cli")

    port = args.port
    logging.info(f'Using port {port}')

    with serial.Serial(port, baudrate=115200, timeout=10) as device:
        logging.info(f"Opened serial port {device.name}")
        msg = getMsg(device)
        decodeMsg(msg)

if __name__ == "__main__":
    main()
