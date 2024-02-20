# pylint: disable=c-extension-no-member

# Note, needs to be run as root, or some other way to have the right permisions. This is complicated
# to do with pyenv, but you can run the program as following in order to get the right python
# to work:
#
# sudo env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python3 tuntest.py

import logging
# import threading
import select
import pytun
# import scapy

from local_comms_consts import LC_COORD_SA #, LC_DATA_PORT

RX_LOOP_TIMEOUT = 1.0
LC_SUBNET = '172.27.27.'
LC_NETMASK = '255.255.255.0'

class LocalComms_Netif():
    # class quit variable will cause any/all instances to quit
    _quit = False
    forward_to_iface = False
    forward_to_lc = False
    route_table = {}

    def __init__(self, serdev, mailbox, shortaddr):
        self.isup = False
        self.device = serdev
        self.mailbox = mailbox
        self.shortaddr = shortaddr
        self.tun = pytun.TunTapDevice(flags=pytun.IFF_TUN|pytun.IFF_NO_PI)
        self.tun.addr = self.ipaddr()
        self.tun.netmask = LC_NETMASK

    def disable(self):
        LocalComms_Netif.forward_to_iface = False
        LocalComms_Netif.forward_to_lc = False
        self.tun.down()
        self.isup = False

    def enable(self):
        LocalComms_Netif.forward_to_iface = True
        LocalComms_Netif.forward_to_lc = True
        self.tun.up()
        self.isup = True

    def ipaddr(self):
        sn = ''
        if self.shortaddr > 254 or self.shortaddr < 0:
            logging.error(f"Unable to create IPv4 address, short adddress out of range: {self.shortaddr}")

        if self.shortaddr == 0:
            sn = LC_SUBNET + '100'
        elif self.shortaddr == LC_COORD_SA:
            sn = LC_SUBNET + '200'
        else:
            sn = LC_SUBNET + str(self.shortaddr)
        return sn

    def send_to_iface(self, data):
        if LocalComms_Netif.forward_to_iface and self.isup:
            self.tun.write(data)

    def _rx_from_iface(self, packet):
        print(f"Rx packet from iface: {packet}")

    def run(self):
        while not LocalComms_Netif._quit:
            sread = [self.tun]
            swrite = []
            sxlist = []
            packet = b''
            if self.isup:
                try:
                    sread, swrite, sxlist = select.select(sread, swrite, sxlist, 0.5)
                    if self.tun in sread:
                        packet = self.tun.read(self.tun.mtu)
                        self._rx_from_iface(packet)
                except OSError as err:
                    logging.error(f"Unexpected OS error: {err}")
                except pytun.Error as err:
                    logging.error(f"Unexpected PyTUN error: {err}")

    def quit(): # pylint: disable=no-method-argument
        LocalComms_Netif.forward_to_iface = True
        LocalComms_Netif.forward_to_lc = True
        LocalComms_Netif._quit = True
