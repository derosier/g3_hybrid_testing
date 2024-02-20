#!/usr/bin/env python3

# Note, needs to be run as root, or some other way to have the right permisions. This is complicated
# to do with pyenv, but you can run the program as following in order to get the right python
# to work:
#
# sudo env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python3 tuntest.py

# pylint: disable=c-extension-no-member

import pytun

# Create a TUN interface
tun = pytun.TunTapDevice(flags=pytun.IFF_TUN|pytun.IFF_NO_PI)

# Set the IP address and netmask for the interface
tun.addr = '172.17.0.1'
tun.netmask = '255.255.255.0'

# Bring up the interface
tun.up()

# Read and process packets from the interface
while True:
    packet = tun.read(tun.mtu)
    print(f"{packet}")
