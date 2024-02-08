#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import signal
import time

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

_G_running = True
def exit_clean():
    global _G_running
    _G_running = False

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    exit_clean()

####################################################################################################
##  MAIN
####################################################################################################

def main():
    logging.debug("*** Starting Local Comms")
    logging.debug(f"args: {args}")

    signal.signal(signal.SIGINT, shutdown_handler)

    while _G_running:
        time.sleep(0.1)

    logging.debug("*** Quitting Local Comms")

if __name__ == "__main__":
    main()
