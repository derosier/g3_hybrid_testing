import logging
import struct

class G3Cmd():
    g3_id = 0xFE  # this is not used in the doc
    g3_name = 'UNKNOWN'
    rx_msgs = []
    def __init__(self, subparsers):
        self.raw = b''
        self.fields = {}
        self.callback = None
        self.rx_got = {}
        self.parser = self._add_parser(subparsers)

    def _add_parser(self, _):
        return False

    def parse_args(self, args):
        logging.debug(f"{self.g3_name}.parse_args({args})")

    def setup_rx(self, supported_rx_msgs):
        logging.debug(f"{self.g3_name}.setup_rx({supported_rx_msgs})")
        for msg in supported_rx_msgs:
            if msg.g3_name in self.rx_msgs:
                self.rx_got[msg.g3_name] = 0
                msg.set_hook(self._callback, self)

    def encode_cmd(self):
        logging.debug(f"{self.g3_name}.encode_cmd()")

    def execute(self):
        logging.debug(f"{self.g3_name}.execute()")

    def set_cb(self, cb):
        logging.debug(f"{self.g3_name}.set_cb to {cb}")
        self.callback = cb

    # The callback is called from the received message hook and because of the way it is done
    # the first parameter will be the actual Resp object. We can ignore this. The next arguments:
    #    self - This is the context set when the hook is set and should be our actual real 'self'
    #    name - The name of the message rx, which would be G3Resp.g3_name
    #    fields - the parsed fields from the message
    def _callback(_, self, name, fields): # pylint: disable=no-self-argument
        logging.debug(f"{self.g3_name}._callback({self}, {name}, {fields})")
        try:
            self.rx_got[name] = self.rx_got[name] + 1
            test_list = []
            for value in self.rx_got.values():
                test_list.append(value > 0)
            if all(test_list):
                if self.callback:
                    self.callback(self.g3_name, fields)
        except KeyError:
            logging.warning("Cmd callback called for non-registered Rx message.")

# Below commands are defined in the Datasheet AN5603 from ST.

# Datasheet pp 55
class DBGToolCmd(G3Cmd):
    g3_id = 0x14
    g3_name = 'HOSTIF-DBGTOOL'
    rx_msgs = ['HOSTIF-DBGTOOL']

    HI_DBG_INFO = 0
    HI_DBG_USART_TRC_CONF = 1
    HI_DBG_LED_CONF = 2

    def _add_parser(self, subparsers):
        return subparsers.add_parser('dbgtool', help='Use debugtool info command')

    def parse_args(self, args):
        self.fields['subcmd'] = self.HI_DBG_INFO

    def encode_cmd(self):
        raw = struct.pack("<B", self.fields['subcmd'])
        if self.fields['subcmd'] > self.HI_DBG_INFO:
            logging.debug(f"Unsupported DBGTOOL subcommand {self.fields['subcmd']}")
        return raw
