import logging
import threading

import msg_types
from local_comms_consts import * # pylint: disable=wildcard-import, unused-wildcard-import

RX_LOOP_TIMEOUT = 1.0

_G_wait_data = threading.Event()
_G_returned_data = {}
# Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan': 30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust', 'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0': [], 'prevhop_media': 0, 'conn_id': 1, 'src_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port': 5000, 'dest_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port': 5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_callback(_, name, fields): # pylint: disable=unused-argument
    global _G_returned_data
    _G_returned_data = fields
    _G_wait_data.set()

class LocalComms_Rx_Handler():
    # class quit variable will cause any/all instances to quit
    _quit = False
    HandleRX = False
    HandledPackets = [msg_types.MSG_TYPE_LC_REQUEST_ID,
                      msg_types.MSG_TYPE_LC_RESPOND_ID,
                      msg_types.MSG_TYPE_LC_LCN_INFORMATION,
                      msg_types.MSG_TYPE_LC_LCN_INFO_CONFIRM,
                      msg_types.MSG_TYPE_LC_SWITCH_NETWORK,
                      msg_types.MSG_TYPE_LC_PAIR_CLEAR]

    def __init__(self, serdev, mailbox):
        self.device = serdev
        self.mailbox = mailbox

    def _rx_packet(self, data):
        print(f"Rx packet {data}")
        message = {}
        if data['dest_port'] == LC_CONTROL_PORT:
            packet = msg_types.decode_packet(data['data'])
            if packet['type'] in LocalComms_Rx_Handler.HandledPackets:
                message['type'] = 'ctrl_packet'
                message['packet'] = packet
                self.mailbox.put(message)
        elif data['dest_port'] == LC_DATA_PORT:
            print("Rx DATA packet")

    def run(self):
        while not LocalComms_Rx_Handler._quit:
            _G_wait_data.clear()
            if not _G_wait_data.wait(RX_LOOP_TIMEOUT):
                continue # timeout here is expected
            if not _G_returned_data['valid_msg']:
                logging.error(f"wait_for_connection - Data Rx but invalid packet: {_G_returned_data['rx_status']}")
                continue
            if LocalComms_Rx_Handler.HandleRX:
                self._rx_packet(_G_returned_data)

    def quit(): # pylint: disable=no-method-argument
        LocalComms_Rx_Handler.HandleRX = False
        LocalComms_Rx_Handler._quit = True
