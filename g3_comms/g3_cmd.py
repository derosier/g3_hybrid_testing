import logging
import struct
import binascii

import g3_comms.g3_consts as G3C
import g3_comms.g3_structs as G3S
import g3_comms.g3_msgs

class G3Cmd():
    g3_id = 0xFE  # this is not used in the doc
    g3_name = 'UNKNOWN'
    rx_msgs = []
    def __init__(self, subparsers=None):
        self.raw = b''
        self.fields = {}
        self.callback = None
        self.rx_got = {}
        self.parser = None
        if subparsers:
            self.parser = self._add_parser(subparsers)

    def _add_parser(self, _):
        return False

    def parse_args(self, args):
        logging.debug(f"{self.g3_name}.parse_args({args})")

    def setup_rx(self, supported_rx_msgs):
        logging.debug(f"{self.g3_name}.setup_rx({supported_rx_msgs})")
        for msg in supported_rx_msgs:
            for rx_msg in self.rx_msgs:
                if msg.g3_name == rx_msg:
                    self.rx_got[msg.g3_name] = 0
                    msg.set_hook(self._callback, self)

    def clean_rx(self, supported_rx_msgs):
        logging.debug(f"{self.g3_name}.clean_rx({supported_rx_msgs})")
        for msg in supported_rx_msgs:
            for rx_msg in self.rx_msgs:
                if msg.g3_name == rx_msg:
                    del self.rx_got[msg.g3_name]
                    msg.clear_hook(self._callback, self)

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

# Datasheet (AN5603) pg 49
class HWResetCmd(G3Cmd):
    g3_id = 0x00
    g3_name = 'HOSTIF-HWRESET'
    rx_msgs = ['HOSTIF-HWRESET']

    def _add_parser(self, subparsers):
        return subparsers.add_parser('hwreset', help='Issue HWReset request')

    def encode_cmd(self):
        logging.debug("HOSTIF-HWRESET.Requst has no data to encode")
        return b''

# Datasheet (AN5603) pg 50
class UARTBaudSetCmd(G3Cmd):
    g3_id = 0x06
    g3_name = 'HOSTIF-BAUDRATESET'
    rx_msgs = ['HOSTIF-BAUDRATESET']

    HI_BAUD_DEFAULT = 921600

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('speed', help=f'Change the UART baudrate, defaults to {self.HI_BAUD_DEFAULT}')
        parser.add_argument('speed', type=int, default=self.HI_BAUD_DEFAULT, help='New UART baud rate')
        return parser

    def parse_args(self, args):
        self.fields['speed'] = args.speed

    def encode_cmd(self):
        raw = struct.pack("<I", self.fields['speed'])
        return raw

# AN5603 Rev 2.22 pg. 67
class TestSetCmd(G3Cmd):
    g3_id = 0x0A
    g3_name = 'HOSTIF-TESTSET'
    rx_msgs = ['HOSTIF-TESTSET']

    def __init__(self, subparsers=None):

        # The Test Set command payload includes a section which is the exact payload of the data send command
        # pertaining to the platform mode we're operating in; so a PHY data rate test will send PHY-DATA commands
        # over and over again.
        # Rather than redefining those payloads, I'm just going to borrow them from the commands we've
        # already declared. This is especially useful for PhyDataCmd which has a lot of fields and would be a tragic
        # copy/paste. If/when we implement MAC or ADP-layer data rate tests we'll have to implement their corresponding
        # single-send commands and can reuse that code here following this pattern.
        self.phy_cmd = PhyDataCmd()
        self.phyrf_cmd = PhyRfCmd()

        # g3_cli passes us a subparsers object to attach subcommands to at initialization; super.__init__() calls
        # _add_parser(), which uses the child Command objects to add sub-sub-commands (as sub-sub-parsers).
        # So we don't pass the subparsers object to those child Command objects (that's the "top level" parser's subparsers,
        # and we want to register them as children to the testset subparser's subparsers), and we need to wait to
        # invoke super.__init__() until we have them instantiated already (so that we can reference them in _add_parser()).
        super().__init__(subparsers=subparsers)

    RXTXCONF_SETTINGS = {
        'rx': 0,
        'tx': 1,
        'tx_randomdelay': 2,  # random delay between 0 and the value in DELAY field (not exactly sure why this is useful)
    }

    RF_SIGNALTYPE = {
        'wave': 0,
        'pn9': 1,
    }

    MODE_PHY_PLC = 0
    MODE_PHY_RF = 6
    MODE_UDP = 4

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('testset', help="Run one of the ST8500's built-in tests")
        parser.add_argument('--rxtxconf', choices=list(self.RXTXCONF_SETTINGS.keys()), default='tx', help="Whether to broadcast or listen to another node's broadcast; default send")
        parser.add_argument('--nbpackets', type=int, default=0xffffffff, help="Number of packets to send (defaults to 0xFFFFFFFF, aka 'just keep going')")
        parser.add_argument('--delay', type=int, default=0, help="In tx mode, delay to add between packets; in tx_randomdelay, the maximum randomized delay to use")

        # How the payload is defined depends on two fields: TESTTYPE and (when TESTTYPE=1) the additional field MODE.
        # I'm representing these both in the CLI as a single-depth subcommand which sets both testtype and mode.

        subparsers = parser.add_subparsers(dest='testtype_mode')  # using 'dest' to remember which subcommand was invoked

        # TESTTYPE = 0: Stop running the test.
        subparsers.add_parser('stop', help="Stop an ongoing test")

        # TESTTYPE = 1: Data Rate, sends packets. Configurable by mode.

        # Mode 0: PHY (which presumably means 'PLC' in this context)
        self.phy_cmd._add_parser(subparsers)  # pylint: disable=protected-access

        # Mode 1/2/3: MAC and ADP layer data rate tests.  **** NOT YET IMPLEMENTED ****

        # Mode 4/5: UDP. Note that the UDP payload format is different from the regular UDP-DATA.Request format, ignoring
        # port and connection ID, so we can't borrow our existing command declaration and need to do it again by hand
        udp_data = subparsers.add_parser('udp', help='UDP-layer data rate test')
        udp_data.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        udp_data.add_argument('--cmdid', type=int, default=0xD0, help="I have no idea what this means actually? AN5603 doesn't explain it at all. Defaults to the command ID 0xD0 for 'UDP-DATA.Request' because maybe that's what they mean?")

        # Mode 6: PHY RF (note that this sends 802.15.4 frames over RF, so higher level than TESTTYPE=4 below)
        self.phyrf_cmd._add_parser(subparsers)  # pylint: disable=protected-access

        # TESTTYPE = 2: INFINITELOOP test type. What does it do? What it says on the tin, I guess!
        subparsers.add_parser('infiniteloop', help="Run an infinite loop w/o payload")

        # TESTTYPE = 3: SECURE_HI test type, which mumble mumble host UART security. **** NOT YET IMPLEMENTED ****

        # TESTTYPE = 4: RF Interface, sends RF signals (not 802.15.4 frames, lower level)
        rf_iface = subparsers.add_parser('rf_signal', help="Low-level RF signal generation")
        rf_iface.add_argument('signaltype', choices=list(self.RF_SIGNALTYPE.keys()), help="Type of signal to generate")

        return parser

    def parse_args(self, args):
        self.fields['rxtxconf'] = self.RXTXCONF_SETTINGS[args.rxtxconf]
        self.fields['nbpackets'] = args.nbpackets
        self.fields['delay'] = args.delay

        # Test type is Table 32, AN5603 Rev 2.22 pg. 67; mode is from Tables 33-37 (and only valid for TESTTYPE=1)
        if args.testtype_mode == 'stop':
            self.fields['test_type'] = 0

        elif args.testtype_mode == PhyDataCmd.SUBPARSER_NAME:
            self.fields['test_type'] = 1
            self.fields['mode'] = self.MODE_PHY_PLC
            self.phy_cmd.parse_args(args)

        elif args.testtype_mode == PhyRfCmd.SUBPARSER_NAME:
            self.fields['test_type'] = 1
            self.fields['mode'] = self.MODE_PHY_RF
            self.phyrf_cmd.parse_args(args)

        elif args.testtype_mode == 'udp':
            self.fields['test_type'] = 1
            self.fields['mode'] = self.MODE_UDP
            self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
            self.fields['cmdid'] = args.cmdid

        elif args.testtype_mode == 'infiniteloop':
            self.fields['test_type'] = 2

        elif args.testtype_mode == 'rf_signal':
            self.fields['test_type'] = 4
            self.fields['signaltype'] = self.RF_SIGNALTYPE[args.signaltype]

    def encode_cmd(self):
        raw = struct.pack("<B", self.fields['test_type'])

        if self.fields['test_type'] == 1:
            raw += struct.pack("<BBII",
                              self.fields['mode'],
                              self.fields['rxtxconf'],
                              self.fields['nbpackets'],
                              self.fields['delay'])

            if self.fields['mode'] == self.MODE_PHY_PLC:
                raw += self.phy_cmd.encode_cmd()

            elif self.fields['mode'] == self.MODE_PHY_RF:
                raw += self.phyrf_cmd.encode_cmd()

            elif self.fields['mode'] == self.MODE_UDP:
                destaddr = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
                length = len(self.fields['data'])
                raw += struct.pack(f"<B16sH{length}s",
                                  self.fields['cmdid'],
                                  destaddr,
                                  length,
                                  self.fields['data'])

        # TESTTYPE=2 seems to have no payload! It's just an infinite loop. You get what you ask for 💁‍♀️

        elif self.fields['test_type'] == 4:
            # nice simple payload, phew!
            raw += struct.pack("<B", self.fields['signaltype'])

        return raw

# AN5603 Rev 2.22 pg. 69
class TestGetCmd(G3Cmd):
    g3_id = 0x0C
    g3_name = 'HOSTIF-TESTGET'
    rx_msgs = ['HOSTIF-TESTGET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('testget', help='Get status of ongoing built-in test')
        return parser

    def encode_cmd(self):
        logging.debug("TESTGET.Request has no data to encode")
        return b''

# Datasheet (AN5603) pg 54
class SFlashCmd(G3Cmd):
    g3_id = 0x0E
    g3_name = 'HOSTIF-SFLASH'
    rx_msgs = ['HOSTIF-SFLASH']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('sflash', help='Read, write, and erase the sflash sectors')
        parser.add_argument('opp',  choices=list(G3C.NVM_OPP.keys()), help=f'SFLASH operation {G3C.NVM_OPP.keys()}')
        parser.add_argument('size', type=int, help='Size of data to read')
        parser.add_argument('address', help='Address in sflash to erase, read or write')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    # args:
    #     opp (string): one of 'erase', 'write', 'read'
    #     section (string): from G3C.NVM_SECTION
    #     offset (int): Integer offset into NVM. See tables 17, 18, 19 pp 17-18
    #     bindata (bytes): For write only, optional data already in b'' format. If not present,
    #                      requires data. Intended for programatic use, so no CLI param.
    #     data (string/bytes): For write only, textual representation of data. Might be a string, or b'', but if
    #                          it starts with '0x' its assumed to be encoded in hex and will be passed
    #                          through bytes.fromhex. If not, it's assumed to be UTF-8. Required
    #                          IIF bindata doesn't exist.
    def parse_args(self, args):
        self.fields['opp'] = G3C.NVM_OPP[args.opp]
        self.fields['address'] = int(args.address, 0)
        self.fields['size'] = args.size
        try:
            self.fields['data'] = args.bindata
        except AttributeError:
            self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)

    def encode_cmd(self):
        length = self.fields['size']
        raw = struct.pack(f"<BHI{length}s", self.fields['opp'], self.fields['size'],
                                            self.fields['address'], self.fields['data'])
        return raw

# Datasheet (AN5603) pg 54
class NVMCmd(G3Cmd):
    g3_id = 0x10
    g3_name = 'HOSTIF-NVM'
    rx_msgs = ['HOSTIF-NVM']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('nvm', help='Read, write, and erase the NVM values')
        self.subparsers = parser.add_subparsers(dest='nvmcmd')
        self.subparsers.add_parser('erase', help="Erase NVM")
        nvmread = self.subparsers.add_parser('read', help="Read value from NVM")
        nvmwrite = self.subparsers.add_parser('write', help="Write value to NVM")
        nvmread.add_argument('section', choices=list(G3C.NVM_SECTION.keys()), help='NVM section')
        nvmread.add_argument('offset', type=int, help='Offset of register to read or write')
        nvmread.add_argument('size', type=int, help='Size of data to read')
        nvmwrite.add_argument('section', choices=list(G3C.NVM_SECTION.keys()), help='NVM section')
        nvmwrite.add_argument('offset', type=int, help='Offset of register to read or write')
        nvmwrite.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    # args:
    #     opp (string): one of 'erase', 'write', 'read'
    #     section (string): from G3C.NVM_SECTION
    #     offset (int): Integer offset into NVM. See tables 17, 18, 19 pp 17-18
    #     bindata (bytes): For write only, optional data already in b'' format. If not present,
    #                      requires data. Intended for programatic use, so no CLI param.
    #     data (string/bytes): For write only, textual representation of data. Might be a string, or b'', but if
    #                          it starts with '0x' its assumed to be encoded in hex and will be passed
    #                          through bytes.fromhex. If not, it's assumed to be UTF-8. Required
    #                          IIF bindata doesn't exist.
    def parse_args(self, args):
        if args.nvmcmd == 'erase':
            self.fields['opp'] = G3C.NVM_OPP['erase']
            return

        self.fields['opp'] = G3C.NVM_OPP[args.nvmcmd]
        self.fields['section'] = G3C.NVM_SECTION[args.section]
        self.fields['offset'] = args.offset
        if args.nvmcmd == 'read':
            self.fields['size'] = args.size
        if args.nvmcmd == 'write':
            try:
                self.fields['data'] = args.bindata
            except AttributeError:
                self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
    def _encode_erase(self):
        raw = struct.pack("<B", self.fields['opp'])
        return raw

    def _encode_read(self):
        raw = struct.pack("<BBHH", self.fields['opp'], self.fields['section'],
                                  self.fields['offset'], self.fields['size'])
        return raw

    def _encode_write(self):
        length = len(self.fields['data'])
        raw = struct.pack(f"<BBHH{length}s", self.fields['opp'], self.fields['section'],
                                            self.fields['offset'], length,
                                            self.fields['data'])
        return raw

    def encode_cmd(self):
        if self.fields['opp'] == G3C.NVM_OPP['erase']:
            return self._encode_erase()
        if self.fields['opp'] == G3C.NVM_OPP['read']:
            return self._encode_read()
        if self.fields['opp'] == G3C.NVM_OPP['write']:
            return self._encode_write()
        return None

# Datasheet (AN5603) pg 55
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

# Datasheet (AN5603) pg 57
class G3RfConfigSetCmd(G3Cmd):
    g3_id = 0x18
    g3_name = 'HOSTIF-RFCONFIGSET'
    rx_msgs = ['HOSTIF-RFCONFIGSET']

    # The RF configuration is complicated, with 25 parameters. Many of these control hardware things
    # that we can't change without causing improper operations or damaging the hardware. The config
    # is also persistent across hardware resets and power-cycles. We're going to only expose some
    # of the parameters to change. The ones that are clearly hardware configuration will be hard
    # set. Everything in the parser will also be set to the defaults we found the boards at, so
    # if you want to keep any changes, you need to specify the values, or if we want new defaults
    # we're going to have to update the parser defaults here.
    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('rfcfgset', help='Set RF configuration')
        parser.add_argument('--basefreq', type=int, default=915000000, help='Base RF frequency')
        parser.add_argument('--mod', type=int, default=0x00, choices=[0x70, 0x00, 0x10, 0xa0, 0x20, 0xB0, 0x30, 0x50, 0x60], help='Modulation, see pg 57')
        parser.add_argument('--datarate', type=int, default=50000, help='Datarate')
        parser.add_argument('--freqdev', type=int, default=12500, help='Frequency division')
        parser.add_argument('--bandwidth', type=int, default=100000, help='Bandwidth')
        parser.add_argument('--csblanking', type=int, default=0x01, choices=[0x00, 0x01], help='Prevents data to be recieved if the RSSI level on the air is below the RSSI threshold')
        parser.add_argument('--rssigain', type=int, default=14, help='Set RSSI filter gain 0-15')
        parser.add_argument('--powerdbm', type=int, default=45, help='Set PA power. 0-45')
        parser.add_argument('--crcmode', type=int, default=0xa0, choices=[0x00, 0x20, 0x40, 0x60, 0x80, 0xa0], help='Select CRC type. See pg 57')
        parser.add_argument('--enfec', type=int, default=0x00, choices=[0x00, 0x01], help='Enable FEC/Viterbi')
        parser.add_argument('--enwhite', type=int, default=0x01, choices=[0x00, 0x01], help='Enable the data whitening')
        parser.add_argument('--eninterleaveing', type=int, default=0x01, choices=[0x00, 0x01], help='Enable interleaving of 802.15.4g packet')
        parser.add_argument('--entxbypass', type=int, default=0x00, choices=[0x00, 0x01], help='Enable FEM Tx bypass mode')
        return parser

    def parse_args(self, args):
        self.fields['radio_base_freq'] = args.basefreq
        self.fields['radio_mod'] = args.mod
        self.fields['radio_datarate'] = args.datarate
        self.fields['radio_freqdev'] = args.freqdev
        self.fields['radio_bandwidth'] = args.bandwidth
        self.fields['radio_csblanking'] = args.csblanking
        self.fields['radio_xtalfreq'] = 50000000
        self.fields['radio_rssigain'] = args.rssigain
        self.fields['powerdbm'] = args.powerdbm
        self.fields['pkt_crcmode'] = args.crcmode
        self.fields['pkt_enfec'] = args.enfec
        self.fields['pkt_enwhitening'] = args.enwhite
        self.fields['pkt_eninterleaving'] = args.eninterleaveing
        self.fields['irq_gpio'] = 3
        self.fields['mcu_clk_en'] = 0
        self.fields['mcu_clk_gpio'] = 0xff
        self.fields['mcu_clk_xoratio'] = 0xff
        self.fields['mcu_clk_rcoratio'] = 0xff
        self.fields['mcu_clk_clockcycles'] = 0xff
        self.fields['extsmps_en'] = 0
        self.fields['fem_en'] = 1
        self.fields['fem_csd_gpio'] = 0
        self.fields['fem_cps_gpio'] = 1
        self.fields['fem_ctx_gpio'] = 2
        self.fields['fem_tx_bypass'] = args.entxbypass

    def encode_cmd(self):
        raw = struct.pack(G3S.RF_CFG,
            self.fields['radio_base_freq'],
            self.fields['radio_mod'],
            self.fields['radio_datarate'],
            self.fields['radio_freqdev'],
            self.fields['radio_bandwidth'],
            self.fields['radio_csblanking'],
            self.fields['radio_xtalfreq'],
            self.fields['radio_rssigain'],
            self.fields['powerdbm'],
            self.fields['pkt_crcmode'],
            self.fields['pkt_enfec'],
            self.fields['pkt_enwhitening'],
            self.fields['pkt_eninterleaving'],
            self.fields['irq_gpio'],
            self.fields['mcu_clk_en'],
            self.fields['mcu_clk_gpio'],
            self.fields['mcu_clk_xoratio'],
            self.fields['mcu_clk_rcoratio'],
            self.fields['mcu_clk_clockcycles'],
            self.fields['extsmps_en'],
            self.fields['fem_en'],
            self.fields['fem_csd_gpio'],
            self.fields['fem_cps_gpio'],
            self.fields['fem_ctx_gpio'],
            self.fields['fem_tx_bypass']
        )
        return raw

# Datasheet (AN5603) pg 58
class G3RfConfigGetCmd(G3Cmd):
    g3_id = 0x1A
    g3_name = 'HOSTIF-RFCONFIGGET'
    rx_msgs = ['HOSTIF-RFCONFIGGET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('rfcfgget', help='Get RF configuration')
        return parser

    def encode_cmd(self):
        logging.debug("HOSTIF-RFCONFIGGET.Requst has no data to encode")
        return b''

# Datasheet (AN5603) pg 62
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

# Datasheet (AN5603) pg 62
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
        logging.debug(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        raw = struct.pack(f"<IHH{length}s", self.fields['id'], self.fields['index'], length, self.fields['data'])
        return raw

# Datasheet (AN5603) pg 63
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

# Datasheet (AN5603) pg 71
class PhyDataCmd(G3Cmd):
    g3_id = 0x40
    g3_name = 'G3PHY-DATA'
    rx_msgs = ['G3PHY-DATA']

    SUBPARSER_NAME = 'phydata'  # as a variable because it's referenced externally by TestSetCmd

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser(self.SUBPARSER_NAME, help='Send data over the PLC phy')
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
        self.fields['tworsblock'] = 0
        self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
        logging.debug(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        preemphasis = binascii.unhexlify('00'*24) # per pg 71 this is all zeros
        raw = struct.pack(f"<BBB24s3sBBH{length}s", self.fields['txpwr'], self.fields['modtype'],
                                                    self.fields['modscheme'], preemphasis,
                                                    self.fields['tonemap'], self.fields['dt'],
                                                    self.fields['tworsblock'], length,
                                                    self.fields['data'])
        return raw

# Datasheet (AN5603) pg 73
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

# Datasheet (AN5603) pg 74
class PhyRfCmd(G3Cmd):
    g3_id = 0x46
    g3_name = 'G3PHY-RF'
    rx_msgs = ['G3PHY-RF']

    SUBPARSER_NAME = 'phyrf'  # as a variable because it's referenced externally by TestSetCmd

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser(self.SUBPARSER_NAME, help='Send data over the RF phy')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    def parse_args(self, args):
        self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)
        logging.debug(self.fields)

    def encode_cmd(self):
        length = len(self.fields['data'])
        raw = struct.pack(f"<H{length}s", length, self.fields['data'])
        return raw

# Datasheet (AN5603) pg 87
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

# Datasheet (AN5603) pg 88
class BootSrvStopCmd(G3Cmd):
    g3_id = 0xB2
    g3_name = 'G3BOOT-SRV-STOP'
    rx_msgs = ['G3BOOT-SRV-STOP']

    def _add_parser(self, subparsers):
        return subparsers.add_parser('bootsrvstop', help='Stop the BOOT server')

    def encode_cmd(self):
        return b''

# Datasheet (AN5603) pg 90
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

# Datasheet (AN5603) pg 89
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

# Datasheet (AN5603) pg 90
class UDPData(G3Cmd):
    g3_id = 0xd0
    g3_name = 'G3UDP-DATA'
    rx_msgs = ['G3UDP-DATA']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('udp', help='Send UDP data')
        parser.add_argument('--connid', required=True, type=int, help='Connection ID')
        parser.add_argument('--handle', required=True, type=int, help='Handle')
        parser.add_argument('data', help="Data as string or hex with '0x' in little endian byte order")
        return parser

    # args:
    #     connid (int): connection id of already created connection via 'G3UDP-CONN-SET'
    #     handle (int): handle, this is just passed in
    #     bindata (bytes): optional data already in b'' format. If not present, requires data
    #     data (string/bytes): textual representation of data. Might be a string, or b'', but if
    #                          it starts with '0x' its assumed to be encoded in hex and will be passed
    #                          through bytes.fromhex. If not, it's assumed to be UTF-8. Required
    #                          IIF bindata doesn't exist.
    def parse_args(self, args):
        if 0 <= args.connid <= 10:
            self.fields['conn_id'] = args.connid
        else:
            logging.error("Invalid connection id")
            raise ValueError
        self.fields['handle'] = args.handle
        try:
            self.fields['data'] = args.bindata
        except AttributeError:
            self.fields['data'] = g3_comms.g3_msgs.parse_data(args.data)

    # Note: we only work with existing connections. Must setup a connection first. All addresses
    # ports, etc will be sent with zeros to tell the firmware to use the connection.
    def encode_cmd(self):
        destaddr = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
        destport = 0
        length = len(self.fields['data'])
        raw = struct.pack(f"<BB16sHH{length}s", self.fields['handle'], self.fields['conn_id'],
                                               destaddr, destport,
                                               length, self.fields['data'])
        return raw

# Datasheet (AN5603) pg 92
class UDPConnSetCmd(G3Cmd):
    g3_id = 0xd3
    g3_name = 'G3UDP-CONN-SET'
    rx_msgs = ['G3UDP-CONN-SET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('connset', help='Setup an UDP connection')
        parser.add_argument('--addr', default=-1, type=int, help="Short address, -1 (default) to accept from all")
        parser.add_argument('--pan', type=int, help="PAN address")
        parser.add_argument('--rport', default=0, type=int, help='Remote port, 0 (default) to accept from any')
        parser.add_argument('--port', type=int, help='Local port')
        parser.add_argument('--connid', type=int, help='Connection id')
        return parser

    def parse_args(self, args):
        # values below are 16 bit, just force the bottom bits and call it good.
        logging.debug(f"set cmd {args}")
        if args.addr == -1:
            self.fields['addr'] = -1
        else:
            self.fields['addr'] = args.addr & 0xffff
        try:
            if args.pan:
                self.fields['pan'] = args.pan & 0xffff
            else:
                self.fields['pan'] = G3C.G3_DEFAULT_PAN
        except AttributeError:
            self.fields['pan'] = G3C.G3_DEFAULT_PAN
        self.fields['remote_port'] = args.rport & 0xffff
        self.fields['local_port'] = args.port & 0xffff
        self.fields['conn_id'] = args.connid

    def encode_cmd(self):
        if self.fields['addr'] == -1:
            self.fields['ipv6addr'] = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
        else:
            self.fields['ipv6addr'] = g3_comms.g3_msgs.hi_ipv6_set_ipaddr(self.fields['addr'], self.fields['pan'])
        logging.debug(f"set encodode ipv6: {self.fields['ipv6addr']}")
        raw = struct.pack("<B16sHH", self.fields['conn_id'], self.fields['ipv6addr'],
                                     self.fields['remote_port'], self.fields['local_port'])
        return raw

# Datasheet (AN5603) pg 92
class UDPConnGetCmd(G3Cmd):
    g3_id = 0xd5
    g3_name = 'G3UDP-CONN-GET'
    rx_msgs = ['G3UDP-CONN-GET']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('connget', help='Get information about an UDP connection')
        parser.add_argument('connid', type=int, help='Connection id')
        return parser

    def parse_args(self, args):
        if 0 <= args.connid <= 10:
            self.fields['conn_id'] = args.connid
        else:
            logging.error("Invalid connection id")
            raise ValueError

    def encode_cmd(self):
        try:
            raw = struct.pack("<B", self.fields['conn_id'])
        except KeyError:
            raw = b''
        return raw

# Datasheet (AN5603) pg 93
class ICMPEchoCmd(G3Cmd):
    g3_id = 0xd7
    g3_name = 'G3ICMP-ECHO'
    rx_msgs = ['G3ICMP-ECHO']

    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('echo', help='Send a ping to remote --addr')
        parser.add_argument('--addr', required=True, type=int, help='Short address')
        parser.add_argument('--pan', type=int, help="PAN address")
        parser.add_argument('--handle', required=True, type=int, help='ICMP Echo handle')
        return parser

    def parse_args(self, args):
        # short addresses are 16 bit, just force the bottom bits and call it good.
        self.fields['addr'] = args.addr & 0xffff
        try:
            if args.pan:
                self.fields['pan'] = args.pan & 0xffff
            else:
                self.fields['pan'] = G3C.G3_DEFAULT_PAN
        except AttributeError:
            self.fields['pan'] = G3C.G3_DEFAULT_PAN
        self.fields['handle'] = args.handle

    def encode_cmd(self):
        self.fields['ipv6addr'] = g3_comms.g3_msgs.hi_ipv6_set_ipaddr(self.fields['addr'], self.fields['pan'])
        raw = struct.pack("<16sBH", self.fields['ipv6addr'], self.fields['handle'], 0)
        return raw
