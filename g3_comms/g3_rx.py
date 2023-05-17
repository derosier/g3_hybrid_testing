import logging
import time

import struct

import pycrc.algorithms

import g3_comms.g3_msgs

G3_HEADER_LEN = 8 # Not including sync bytes
G3_TAG_LEN = 8
G3_CRC_LEN = 2

crc = pycrc.algorithms.Crc(width = 16, poly = 0x1021,
                           reflect_in = False, xor_in = 0x0,
                           reflect_out = False, xor_out = 0x0)

class G3Rx():
    # class quit variable will cause any/all instances to quit
    _quit = False

    def __init__(self, serdev):
        self.device = serdev

    def sync_msg(self):
        got_sync = False
        logging.debug("syncMsg")
        one = b''
        while not G3Rx._quit:
            while (one.hex() != '16') and (not G3Rx._quit):
                one = self.device.read(1)
                if len(one) < 1:
                    time.sleep(0.1)
            if len(one) == 1:
                logging.debug('got first sync')
                two = self.device.read(1)
                if two.hex() == '16':
                    logging.debug('got second sync')
                    got_sync = True
                    break
                logging.debug('not second, resync')
        return got_sync

    def get_msg(self):
        logging.debug("getMsg")
        msg = {}
        if self.sync_msg():
            header = self.device.read(G3_HEADER_LEN)
            if len(header) != G3_HEADER_LEN:
                logging.error(f"Invalid header: {header.hex(' ')}")
                return msg

            up_header = struct.unpack("<BHBI", header)
            msg['cmd'] = up_header[0]
            msg['size'] = up_header[1]
            msg['sec_mode'] = up_header[2]
            msg['counter'] = up_header[3]

            msg['data'] = self.device.read(msg['size'])
            data_len = len(msg['data'])
            if data_len < msg['size']:
                logging.error(f"Short data. {data_len} of msg['size']")
                return None

            if msg['sec_mode'] > 0:
                check_len = G3_TAG_LEN + G3_CRC_LEN
            else:
                check_len = G3_CRC_LEN
            check = self.device.read(check_len)
            if len(check) < check_len:
                logging.error("Invalid check length")
                return None
            if msg['sec_mode'] > 0:
                up_check = struct.unpack("<QH", check)
                msg['sec_tag'] = up_check[0]
                msg['crc'] = up_check[1]
                sec_tag = up_check[0]
            else:
                up_check = struct.unpack("<H", check)
                msg['crc'] = up_check[0]
                msg['sec_tag'] = 0
                sec_tag = b''

            syncro = b'\x16\x16'
            computed_crc = crc.bit_by_bit_fast(syncro + header + msg['data'] + sec_tag)
            logging.debug(f"CRC computed {computed_crc:04x}, CRC Rx {msg['crc']:04x}")
            # TODO: check the CRC
            if computed_crc != msg['crc']:
                return None

            return msg
        else:
            return None

    def run(self):
        while not G3Rx._quit:
            msg = self.get_msg()
            g3_comms.g3_msgs.decodeMsg(msg)
            time.sleep(0.1)

    def quit(): # pylint: disable=no-method-argument
        G3Rx._quit = True
