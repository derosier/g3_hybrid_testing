#!/usr/bin/env python3

# Note, needs to be run as root, or some other way to have the right permisions. This is complicated
# to do with pyenv, but you can run the program as following in order to get the right python
# to work:
#
# sudo env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python3 test_netif.py

import logging
import threading
import queue
import time
import signal

import local_comms_netif

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level='DEBUG',
                    datefmt="%H:%M:%S")

_G_running = True
def exit_clean():
    global _G_running
    _G_running = False

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    exit_clean()


def main():
    logging.info("*** Starting test_netif")

    signal.signal(signal.SIGINT, shutdown_handler)

    # setup basic bindings, unused right now
    mailbox = queue.Queue()
    serial_device = None
    shortaddr = 65

    netif = local_comms_netif.LocalComms_Netif(serial_device, mailbox, shortaddr)
    netif_thread = threading.Thread(target=netif.run)
    netif_thread.start()

    netif.enable()

    while _G_running:
        time.sleep(0.5)

    local_comms_netif.LocalComms_Netif.quit()
    netif_thread.join()

if __name__ == "__main__":
    main()
