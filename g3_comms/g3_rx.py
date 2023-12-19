import logging
import time
import struct

import g3_comms.g3_msgs
from g3_comms.g3_crc import crc16

G3_HEADER_FMT = "<BHBI"
G3_TAG_FOOTER_FMT = "<QH"
G3_NOTAG_FOOTER_FMT = "<H"

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
        msg = {'cmd': 0xFD, 'rx_status': 'OK', 'size': 0, 'data': b'', 'crc':0, 'computed_crc':0xFFFF} # strange init, but useful patern for return
        if self.sync_msg():
            size_left = struct.calcsize(G3_HEADER_FMT)
            header = b''
            while size_left > 0:
                data_rd = self.device.read(size_left)
                header = header + data_rd
                size_left = size_left - len(data_rd)

            up_header = struct.unpack(G3_HEADER_FMT, header)
            msg['cmd'] = up_header[0]
            msg['size'] = up_header[1]
            msg['sec_mode'] = up_header[2]
            msg['counter'] = up_header[3]

            size_left = msg['size']
            data = b''
            while size_left > 0:
                data_rd = self.device.read(size_left)
                data = data + data_rd
                size_left = size_left - len(data_rd)
            msg['data'] = data

            if msg['sec_mode'] > 0:
                size_left = struct.calcsize(G3_TAG_FOOTER_FMT)
            else:
                size_left = struct.calcsize(G3_NOTAG_FOOTER_FMT)
            check = b''
            while size_left > 0:
                data_rd = self.device.read(size_left)
                check = check + data_rd
                size_left = size_left - len(data_rd)

            if msg['sec_mode'] > 0:
                up_check = struct.unpack(G3_TAG_FOOTER_FMT, check)
                msg['sec_tag'] = up_check[0]
                msg['crc'] = up_check[1]
                sec_tag = up_check[0]
            else:
                up_check = struct.unpack(G3_NOTAG_FOOTER_FMT, check)
                msg['crc'] = up_check[0]
                msg['sec_tag'] = 0
                sec_tag = b''

            syncro = b'\x16\x16'
            computed_crc = crc16.bit_by_bit_fast(syncro + header + msg['data'] + sec_tag)
            msg['computed_crc'] = computed_crc
            logging.debug(f"CRC computed {computed_crc:04x}, CRC Rx {msg['crc']:04x}")
            if computed_crc != msg['crc']:
                msg['rx_status'] = 'BAD CRC'
            return msg
        else:
            return None

    def run(self):
        while not G3Rx._quit:
            msg = self.get_msg()
            g3_comms.g3_msgs.decodeMsg(msg)

    def quit(): # pylint: disable=no-method-argument
        G3Rx._quit = True
