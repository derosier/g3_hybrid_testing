#!/usr/bin/env python3

import logging
import argparse
import threading
import signal

import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
from g3_comms import g3_cmd

default_port="/dev/ttyACM0"

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest='cmd')
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-d", "--dump", action="store_true", help="Dump all messages recieved, sniffer mode")
parser.add_argument("-n", "--count", type=int, default=0, help="Number of times to repeat a command or to recieve messages")

# Instantiate a global instance of every response we want to process on Rx
resp_HWReset = g3_resp.HWResetResp()
resp_DBGTool = g3_resp.DBGToolResp()
g3_comms.g3_msgs.msg_decode_list.append(resp_HWReset)
g3_comms.g3_msgs.msg_decode_list.append(resp_DBGTool)

# Instantiate a global instance of every command we might want to send
g3_comms.g3_msgs.msg_cmds['dbgtool'] = g3_cmd.DBGToolCmd(subparsers)

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

    logging.debug(f"Registered messages for decode: {g3_comms.g3_msgs.msg_decode_list}")
    logging.debug(f"Registered commands to tx: {g3_comms.g3_msgs.msg_cmds.keys()}")
    device = serial.Serial(port, baudrate=115200, timeout=0)
    logging.info(f"Opened serial port {device.name}")

    rx_protocol = g3_comms.g3_rx.G3Rx(device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    # Now that we can Rx responses, now process and run commands
    logging.debug(f"Command entered {args.cmd}")
    if args.cmd:
        try:
            g3_comms.g3_msgs.msg_cmds[args.cmd].parse_args(args)
            g3_comms.g3_msgs.msg_cmds[args.cmd].setup_rx(g3_comms.g3_msgs.msg_decode_list)
            g3_comms.g3_tx.send_and_wait(device, g3_comms.g3_msgs.msg_cmds[args.cmd])
        except KeyError:
            print(f"Unrecognized command {args.cmd}. Exiting.")
        g3_comms.g3_rx.G3Rx.quit()

    # Cleanup and quit
    rx_thread.join()

if __name__ == "__main__":
    main()
