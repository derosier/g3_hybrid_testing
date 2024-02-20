# pylint: disable=c-extension-no-member

# Note, needs to be run as root, or some other way to have the right permisions. This is complicated
# to do with pyenv, but you can run the program as following in order to get the right python
# to work:
#
# sudo env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python3 tuntest.py

import logging
import select
import pytun
from scapy.all import IP # pylint: disable=no-name-in-module

import g3_comms.g3_lib
from local_comms_consts import LC_COORD_SA, LC_PAIR_SA, LC_DATA_PORT, LC_DATA_MIN_PACKET_NUM, LC_DATA_MAX_PACKET_NUM

RX_LOOP_TIMEOUT = 1.0
LC_SUBNET = '172.27.0.'
LC_NETMASK = '255.255.255.0'

def sa_from_ip(ipaddr):
    # This assumes it's a valid IPv4!
    print(f"Packet dest ip: {ipaddr}")
    octets = ipaddr.split('.')
    sa = int(octets[3])
    if sa == 100:
        sa = 0
    elif sa == 200:
        sa = LC_COORD_SA
    elif sa == 250:
        sa = LC_PAIR_SA
    return sa

class LocalComms_Netif():
    # class quit variable will cause any/all instances to quit
    _quit = False
    forward_to_iface = False
    forward_to_lc = False
    route_table = {}

    def __init__(self, serdev, connman, shortaddr):
        self.isup = False
        self.serial_device = serdev
        self.connman = connman
        self.shortaddr = shortaddr
        self.tun = pytun.TunTapDevice(flags=pytun.IFF_TUN|pytun.IFF_NO_PI)
        self.tun.addr = self.myipaddr()
        self.tun.netmask = LC_NETMASK
        self._packet_num = LC_DATA_MIN_PACKET_NUM

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

    def change_shortaddr(self, sa):
        self.shortaddr = sa
        self.tun.addr = self.myipaddr()
        self.tun.netmask = LC_NETMASK

    def myipaddr(self):
        sn = ''

        if self.shortaddr == 0:
            sn = LC_SUBNET + '100'
        elif self.shortaddr == LC_COORD_SA:
            sn = LC_SUBNET + '200'
        elif self.shortaddr == LC_PAIR_SA:
            sn = LC_SUBNET + '250'
        elif self.shortaddr <= 254 and self.shortaddr >= 0:
            sn = LC_SUBNET + str(self.shortaddr)
        else:
            logging.error(f"Unable to create IPv4 address, short adddress out of range: {self.shortaddr}")
        return sn

    def send_to_iface(self, data):
        # This should be called with data unmodified and for us to just pass to the interface.
        # It was a valid packet on the other end, so it's supposed to still be intact.
        if LocalComms_Netif.forward_to_iface and self.isup:
            self.tun.write(data)

    def _get_next_packet_number(self):
        self._packet_num = self._packet_num + 1
        if self._packet_num > LC_DATA_MAX_PACKET_NUM:
            self._packet_num = LC_DATA_MIN_PACKET_NUM
        return self._packet_num

    def send_packet_to_g3(self, dest, data):
        # These packets go without any header at all. Anything that gets sent to/from the DATA
        # port is just raw data wrapped in the G3 UDP and we don't have to do anything other than
        # send_udp on it. Addresses and ports are handled by the connection manager.
        logging.info(f"Sending data packet to {dest}")
        connid = self.connman.new_conn(self.serial_device, dest, LC_DATA_PORT, LC_DATA_PORT)
        # Send the packet
        packet_num = self._get_next_packet_number()
        (send_ok, status) = g3_comms.g3_lib.send_udp(self.serial_device, connid, packet_num, data)
        if not send_ok:
            logging.error(f"Error sending data packet: {status}")

        # Cleanup connection
        self.connman.del_connection(self.serial_device, connid)

    def _rx_from_iface(self, packet):
        if not LocalComms_Netif.forward_to_lc:
            return
        if not self.isup:
            return
        logging.debug(f"Rx packet from iface: {packet}")

        # First, we need to grab the destination ID for our routing.  For now, we'll route
        # everything, but we still need the destination.
        decoded = IP(packet)
        if decoded.version == 4:
            print(f"Rx IPv4 packet from iface: {packet}")
            # Right now, we're only handling IPv4
            dest_ip = decoded.dst
            dest_sa = sa_from_ip(dest_ip)
            # next three lines fixes up the dest IP. In order to force Linux to "route" the packet
            # over the interface, but not simply loopback in the case we're running both sides on
            # the same computer, we set the IP address with 0 as the third octet, but when addressing
            # packets in the user-space program, use a 1 or higher in the third octet.  Since our
            # subnet considers that significant, we should get routed over the base interface. This
            # requires setting up the routes correctly however.
            new_dest_ip = LC_SUBNET + str(dest_sa)
            decoded.dst = new_dest_ip
            packet = bytes(decoded)
            print(f"Packet to send to node {dest_sa}")
            self.send_packet_to_g3(dest_sa, packet)

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
