import logging
import struct
import binascii

import g3_comms.g3_consts as G3C
import g3_comms.g3_msgs

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

# Datasheet pg 49
class HWResetCmd(G3Cmd):
    g3_id = 0x00
    g3_name = 'HOSTIF-HWRESET'
    rx_msgs = ['HOSTIF-HWRESET']

    def _add_parser(self, subparsers):
        return subparsers.add_parser('hwreset', help='Issue HWReset request')

    def encode_cmd(self):
        logging.debug("HOSTIF-HWRESET.Requst has no data to encode")
        return b''

# Datasheet pg 55
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

# Datasheet pg 62
class G3GetCmd(G3Cmd):
    g3_id = 0x20
    g3_name = 'G3LIB-GET'
    rx_msgs = ['G3LIB-GET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('get', help='Get attribute from G3Lib PIB')
        parser.add_argument('--id', type=lambda x: int(x,0), required=True, help='PIB attribute ID')
        parser.add_argument('--index', type=lambda x: int(x,0), default=0, help='Entry index if attribute is a table.')
        return parser

    def parse_args(self, args):
        self.fields['id'] = args.id
        self.fields['index'] = args.index

    def encode_cmd(self):
        raw = struct.pack("<IH", self.fields['id'], self.fields['index'])
        return raw

# Datasheet pg 62
class G3SetCmd(G3Cmd):
    g3_id = 0x22
    g3_name = 'G3LIB-SET'
    rx_msgs = ['G3LIB-SET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('set', help='Set attribute in G3Lib PIB')
        parser.add_argument('--id', type=lambda x: int(x,0), required=True, help='PIB attribute ID')
        parser.add_argument('--index', type=lambda x: int(x,0), default=0, help='Entry index if attribute is a table.')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    def parse_args(self, args):
        self.fields['id'] = args.id
        self.fields['index'] = args.index
        self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
        print(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        raw = struct.pack(f"<IHH{length}s", self.fields['id'], self.fields['index'], length, self.fields['data'])
        return raw

# Datasheet pg 63
class SWResetCmd(G3Cmd):
    g3_id = 0x24
    g3_name = 'G3LIB-SWRESET'
    rx_msgs = ['G3LIB-SWRESET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('swreset', help='Perform a software reset and change the PLC configuration')
        parser.add_argument('--bandplan', default='FCC', choices=['FCC', 'C-A', 'C-B'], help='What PLC band to operate on. Default is FCC.')
        parser.add_argument('--devicetype', default='device', choices=['device', 'dev', 'coordinator', 'coord'], help='Start as a "device" node (default) or network "coordinator".')
        parser.add_argument('--mode', default='boot', choices=list(G3C.G3_MODE.keys()), help='What API mode to boot into')
        return parser

    def parse_args(self, args):
        if args.bandplan == 'FCC':
            self.fields['bandplan'] = 3
        elif args.bandplan == 'C-A':
            self.fields['bandplan'] = 0
        elif args.bandplan == 'C-B':
            self.fields['bandplan'] = 1
        else:
            logging.warning(f"Unknown bandplan {args.bandplan}, using 'FCC'")
            self.fields['bandplan'] = 3

        if args.devicetype in ('device', 'dev'):
            self.fields['devicetype'] = 0
        elif args.devicetype in ('coordinator', 'coord'):
            self.fields['devicetype'] = 1
        else:
            logging.warning(f"Unknown devicetype {args.devicetype}, using 'device'")
            self.fields['devicetype'] = 0

        try:
            self.fields['mode'] = G3C.G3_MODE[args.mode]
        except KeyError:
            logging.warning(f"Unknown platform mode {args.mode}, using 'boot'")
            self.fields['mode'] = G3C.G3_MODE['boot']

    def encode_cmd(self):
        raw = struct.pack("<BBB", self.fields['bandplan'], self.fields['devicetype'], self.fields['mode'])
        return raw

# Datasheet pg 71
class PhyDataCmd(G3Cmd):
    g3_id = 0x40
    g3_name = 'G3PHY-DATA'
    rx_msgs = ['G3PHY-DATA']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('phydata', help='Send data over the phy')
        parser.add_argument('--txpwr', default=16, type=int, help='Set Tx power. 0-32. Default 16.')
        parser.add_argument('--modtype', default='Robust', choices=list(G3C.G3_PHY_MODTYPE_R.keys()), help='Modulation type')
        parser.add_argument('--modscheme', default='Differential', choices=list(G3C.G3_PHY_MODSCHEME_R.keys()), help='Modulation scheme')
        parser.add_argument('--tonemap', default='ffffff', help='Tonemap, six bare hex digits eg "ffffff" (default)')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    def parse_args(self, args):
        if args.txpwr < 0:
            logging.warning("txpwr is too low, pinning to 0")
        elif args.txpwr > 0x20:
            logging.warning("txpwr is too high, clampping to 32")
        self.fields['txpwr'] = args.txpwr
        self.fields['modtype'] = G3C.G3_PHY_MODTYPE_R[args.modtype]
        self.fields['modscheme'] = G3C.G3_PHY_MODSCHEME_R[args.modscheme]
        if len(args.tonemap) != 6:
            logging.warning("Invlid tonemap, using ffffff")
            args.tonemap = 'ffffff'
        try:
            self.fields['tonemap'] = binascii.unhexlify(args.tonemap)
        except binascii.Error:
            logging.warning("Invlid tonemap, using ffffff")
            args.tonemap = 'ffffff'
            self.fields['tonemap'] = binascii.unhexlify(args.tonemap)
        self.fields['dt'] = 1
        self.fields['twosrsblock'] = 0
        self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
        print(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        preemphasis = binascii.unhexlify('00'*24) # per pg 71 this is all zeros
        raw = struct.pack(f"<BBB24s3sBBH{length}s", self.fields['txpwr'], self.fields['modtype'],
                                                    self.fields['modscheme'], preemphasis,
                                                    self.fields['tonemap'], self.fields['dt'],
                                                    self.fields['tworsblock'], length,
                                                    self.fields['data'])
        return raw

# Datasheet pg 73
class PhyAckCmd(G3Cmd):
    g3_id = 0x43
    g3_name = 'G3PHY-ACK'
    rx_msgs = ['G3PHY-ACK']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('phyack', help='Send a phy ack')
        parser.add_argument('--fcs', default='0000', help='FCS')
        parser.add_argument('--type', default='ack', choices=['ack', 'nack'], help='ack or nack the last packet')
        parser.add_argument('--avoid', default=0, type=int, help='Collision avoidance (0:no, 1:yes)')
        return parser

    def parse_args(self, args):
        if len(args.fcs) != 4:
            logging.warning("Invalid FCS, using 000000")
            args.fcs = '0000'
        try:
            self.fields['fcs'] = binascii.unhexlify(args.fcs)
        except binascii.Error:
            logging.warning("Invalid FCS, using 000000")
            self.fields['fcs'] = b'\x00\x00'
        if args.type == 'ack':
            ack = 0x02 # ack
        else:
            ack = 0x03 # nack
        avoid = 0x00
        if args.avoid == 1:
            avoid = 0x04
        self.fields['dt_ssca'] = 0x00 | ack | avoid
        self.fields['crc5_8'] = 0x00 # don't really know what to calc over, so just holding space right now

    def encode_cmd(self):
        raw = struct.pack("<HBB", self.fields['fcs'], self.fields['dt_ssca'], self.fields['crc5_8'])
        return raw

# Datasheet pg 74
class PhyRfCmd(G3Cmd):
    g3_id = 0x46
    g3_name = 'G3PHY-RF'
    rx_msgs = ['G3PHY-RF']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('phyrf', help='Send data over the RF')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    def parse_args(self, args):
        self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
        print(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        raw = struct.pack(f"<H{length}s", length, self.fields['data'])
        return raw

# Datasheet pg 87
class BootSrvStartCmd(G3Cmd):
    g3_id = 0xB0
    g3_name = 'G3BOOT-SRV-START'
    rx_msgs = ['G3BOOT-SRV-START']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('bootsrvstart', help='Start the BOOT server')
        parser.add_argument('--addr', required=True, type=int, help='Short address, 16 bit')
        parser.add_argument('--panid', required=True, type=int, help='PAN Id of the network to start; 16 bit')
        parser.add_argument('--reqtype', default='normal', choices=['normal', 'fast'], help='Request type [0 normal, 1 fast restore]')
        return parser

    def parse_args(self, args):
        if args.reqtype == 'normal':
            self.fields['reqtype'] = 0
        elif args.reqtype == 'fast':
            self.fields['reqtype'] = 1
        else:
            logging.warning(f"Unknown boot srv start type {args.reqtype}, using 'normal'")
            self.fields['reqtype'] = 0
        # both addresses are 16 bit, just force the bottom bits and call it good.
        self.fields['addr'] = args.addr & 0xffff
        self.fields['panid'] = args.panid & 0xffff

    def encode_cmd(self):
        raw = struct.pack("<HHB", self.fields['addr'], self.fields['panid'], self.fields['reqtype'])
        return raw

# Datasheet pg 90
class BootDevStartCmd(G3Cmd):
    g3_id = 0xB8
    g3_name = 'G3BOOT-DEV-START'
    rx_msgs = ['G3BOOT-DEV-START']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('bootdevstart', help='Start the BOOT device mode')
        parser.add_argument('--reqtype', default='normal', choices=['normal', 'fast'], help='Request type [0 normal, 1 fast restore]')
        return parser

    def parse_args(self, args):
        if args.reqtype == 'normal':
            self.fields['reqtype'] = 0
        elif args.reqtype == 'fast':
            self.fields['reqtype'] = 1
        else:
            logging.warning(f"Unknown boot srv start type {args.reqtype}, using 'normal'")
            self.fields['reqtype'] = 0

    def encode_cmd(self):
        raw = struct.pack("<B", self.fields['reqtype'])
        return raw

# Datasheet pg 89
class BootSrvSetPSKCmd(G3Cmd):
    g3_id = 0xC5
    g3_name = 'G3BOOT-SRV-SETPSK'
    rx_msgs = ['G3BOOT-SRV-SETPSK']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('bootsetpsk', help='Set the PSK for the boot server')
        parser.add_argument('--addr', required=True, type=int, help='Short address, 16 bit')
        parser.add_argument('--longaddr', required=True, type=int, help='Extended address, 64 bit')
        parser.add_argument('--psk', required=True, help='PSK Up to 16 bytes')
        return parser

    def parse_args(self, args):
        # extended addresses are 64 bit, just force the bottom bits and call it good.
        self.fields['extd_addr'] = args.addr & 0xffffffffffffffff
        # short addresses are 16 bit, just force the bottom bits and call it good.
        self.fields['addr'] = args.addr & 0xffff
        self.fields['psk'] = bytes(args.psk, 'utf-8')

    def encode_cmd(self):
        # PSK field is 16 bytes. Pack automatically truncates it or pads it with 0x00 if necessary
        raw = struct.pack("<Q16sH", self.fields['extd_addr'], self.fields['psk'], self.fields['addr'])
        return raw

# Datasheet pg 93
class ICMPEchoCmd(G3Cmd):
    g3_id = 0xd7
    g3_name = 'G3ICMP-ECHO'
    rx_msgs = ['G3ICMP-ECHO']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('echo', help='Send a ping to remote --addr')
        parser.add_argument('--addr', required=True, type=int, help='Short address')
        parser.add_argument('--handle', required=True, type=int, help='ICMP Echo handle')
        return parser

    def parse_args(self, args):
        # short addresses are 16 bit, just force the bottom bits and call it good.
        self.fields['addr'] = args.addr & 0xffff
        self.fields['handle'] = args.handle

    def encode_cmd(self):
        self.fields['ipv6addr'] = g3_comms.g3_msgs.hi_ipv6_set_ipaddr(self.fields['addr'])
        raw = struct.pack("<16sBH", self.fields['ipv6addr'], self.fields['handle'], 0)
        return raw
