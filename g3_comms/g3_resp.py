import logging
import struct

import g3_comms.g3_consts as G3C
import g3_comms.g3_structs as G3S

class G3Resp():
    g3_id = 0xFE  # this is not used in the doc
    g3_name = 'UNKNOWN'
    def __init__(self):
        self.callbacks = [] # List of tupples, (callback, context)
        self.raw_msg = {}
        self.raw_fields = []
        self.fields = {}
        self.valid_msg = False

    def decode(self, msg):
        self.raw_msg = msg
        self.fields['error_code'] = struct.unpack_from("<B", msg['data'])[0]

    def pr_decode(self):
        logging.debug(f'Msg {self.g3_name} (0x{self.g3_id:02x}): {self.fields}')

    def set_hook(self, callback, context):
        logging.debug(f'{self.g3_name} setting callback[{len(self.callbacks)}] to {context}.{callback}')
        self.callbacks.append((callback, context))

    def clear_hook(self, callback, context):
        logging.debug(f'{self.g3_name} clearing callback to {callback}')
        try:
            self.callbacks.remove((callback, context))
        except ValueError:
            logging.warning(f'{self.g3_name} can not find callback {context}.{callback}')

    def call_hook(self):
        fields = {}
        if not self.valid_msg:
            fields = self.raw_msg
        else:
            fields = self.fields
        fields['valid_msg'] = self.valid_msg
        for callback in self.callbacks:
            callback[0](callback[1], self.g3_name, fields)

# Below responses are defined in the Datasheet AN5603 from ST.

# Datasheet pg 49
class HWResetResp(G3Resp):
    g3_id = 0x01
    g3_name = 'HOSTIF-HWRESET'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        if raw_fields[0] == 1:
            self.fields['security_code'] = 'get/set'
        elif raw_fields[0] == 2:
            self.fields['security_code'] = 'all'
        else:
            self.fields['security_code'] = 'none'

# Datasheet pg 50
class UARTBaudSetResp(G3Resp):
    g3_id = 0x07
    g3_name = 'HOSTIF-BAUDRATESET'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BI", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['speed'] = raw_fields[1]

# Datasheet pg 56
class DBGToolResp(G3Resp):
    g3_id = 0x15
    g3_name = 'HOSTIF-DBGTOOL'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<IIIQIBBBBBHH", msg['data'], 1)
        self.raw_fields = raw_fields
        self.fields['g3info'] = raw_fields[0]
        self.fields['lib_version'] = raw_fields[1]
        self.fields['rte_version'] = raw_fields[2]
        self.fields['mac'] = raw_fields[3]
        self.fields['spi_flash_id'] = raw_fields[4]
        self.fields['uart'] = raw_fields[5]
        self.fields['led'] = raw_fields[6]
        if raw_fields[7] == 0x00:
            self.fields['platform'] = 'INVALID'
        elif raw_fields[7] == 0x01:
            self.fields['platform'] = 'STCOMET/STCOM'
        elif raw_fields[7] == 0x02:
            self.fields['platform'] = 'ST8500'
        elif raw_fields[7] == 0xFF:
            self.fields['platform'] = 'none'
        else:
            self.fields['platform'] = 'UNKNOWN 0x[raw_fields[7]:02x]'
        self.fields['rf_connect'] = raw_fields[8]
        self.fields['platform_mode'] = raw_fields[9]
        self.fields['pan_id'] = raw_fields[10]
        self.fields['short_id'] = raw_fields[11]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 62
class G3GetResp(G3Resp):
    g3_id = 0x21
    g3_name = 'G3LIB-GET'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BIHH", msg['data'], 1)
        self.raw_fields = list(raw_fields)
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['id'] = raw_fields[1]
        self.fields['index'] = raw_fields[2]
        self.fields['length'] = raw_fields[3]
        if self.fields['length'] > 0:
            if self.fields['length'] in [*G3C.G3LIB_PIB_VALUE_FORMAT]:
                raw_data = struct.unpack_from(G3C.G3LIB_PIB_VALUE_FORMAT[self.fields['length']], msg['data'], 10)
            else:
                raw_data = struct.unpack_from(f"<{self.fields['length']}s", msg['data'], 10)
            self.raw_fields.append(raw_data[0])
            self.fields['data'] = raw_data[0]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 63
class G3SetResp(G3Resp):
    g3_id = 0x23
    g3_name = 'G3LIB-SET'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BIH", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['id'] = raw_fields[1]
        self.fields['index'] = raw_fields[2]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 56
class SWResetResp(G3Resp):
    g3_id = 0x25
    g3_name = 'G3LIB-SWRESET'

    bandplan_tag = {
        0: 'Cenelec-A',
        1: 'Cenelec-B',
        3: 'FCC'
    }

    device_tag = {
        0: 'device',
        1: 'coordinator'
    }

    def decode(self, msg):
        # Note, the mode field always seems to return 3 for either a setting of 3 or 5
        # and 2 for a setting of 2 and 4. Bug or interesting behavior?  dbgtool does
        # return the correct code for mode.
        super().decode(msg)
        raw_fields = struct.unpack_from("<BBBB", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

        try:
            self.fields['bandplan'] = self.bandplan_tag[raw_fields[1]]
            self.fields['devicetype'] = self.device_tag[raw_fields[2]]
            self.fields['mode'] = G3C.G3_MODE_R[raw_fields[3]]
        except KeyError:
            logging.error(f"Invalid data when decoding {self.g3_name} data: {msg['data']}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Table 95. pg 69
def decode_mac_beacon(msg, offset):
    raw_fields = struct.unpack_from("<BHQBHQBBBH", msg, offset)
    fields = {}
    fields['src_addrmode'] = raw_fields[0]
    fields['src_panid'] = raw_fields[1]
    fields['src_addr'] = raw_fields[2]
    fields['dst_addrmode'] = raw_fields[3]
    fields['dst_panid'] = raw_fields[4]
    fields['dst_addr'] = raw_fields[5]
    fields['mediatype'] = raw_fields[6]
    fields['lqi'] = raw_fields[7]
    fields['bsn'] = raw_fields[8]
    fields['rc_coord'] = raw_fields[9]
    return fields

# Table 96. pg 70
def decode_mac_data(msg, offset):
    fmt = "<BHQBHQBBBBBBH"
    raw_fields = struct.unpack_from(fmt, msg, offset)
    fields = {}
    fields['src_addrmode'] = raw_fields[0]
    fields['src_panid'] = raw_fields[1]
    fields['src_addr'] = raw_fields[2]
    fields['dst_addrmode'] = raw_fields[3]
    fields['dst_panid'] = raw_fields[4]
    fields['dst_addr'] = raw_fields[5]
    fields['mediatype'] = raw_fields[6]
    fields['lqi'] = raw_fields[7]
    fields['dsn'] = raw_fields[8]
    fields['sec_level'] = raw_fields[9]
    fields['keyindex'] = raw_fields[10]
    fields['qos'] = raw_fields[11]
    fields['msdulen'] = raw_fields[12]
    offset = offset + struct.calcsize(fmt)
    fields['msdu'] = msg[offset:]
    if len(fields['msdu']) != fields['msdulen']:
        logging.error("msdu len mismatch")
    return fields

# Table 97. pg 70
def decode_mac_cmd(msg, offset):
    fmt = "<BHQBHQBBB"
    raw_fields = struct.unpack_from(fmt, msg, offset)
    fields = {}
    fields['src_addrmode'] = raw_fields[0]
    fields['src_panid'] = raw_fields[1]
    fields['src_addr'] = raw_fields[2]
    fields['dst_addrmode'] = raw_fields[3]
    fields['dst_panid'] = raw_fields[4]
    fields['dst_addr'] = raw_fields[5]
    fields['mediatype'] = raw_fields[6]
    fields['lqi'] = raw_fields[7]
    fields['cmd_frame_id'] = raw_fields[8]
    offset = offset + struct.calcsize(fmt)
    fields['cmd_payload'] = msg[offset:]
    return fields

# Table 98. pg 71
def decode_mac_rf_ack(msg, offset):
    raw_fields = struct.unpack_from("<BHQBHQBB", msg, offset)
    fields = {}
    fields['src_addrmode'] = raw_fields[0]
    fields['src_panid'] = raw_fields[1]
    fields['src_addr'] = raw_fields[2]
    fields['dst_addrmode'] = raw_fields[3]
    fields['dst_panid'] = raw_fields[4]
    fields['dst_addr'] = raw_fields[5]
    fields['lqi'] = raw_fields[6]
    fields['ack_value'] = raw_fields[7]
    return fields

# Table 101. pg 72
def decode_phy_data(msg, offset):
    fmt = "<72sBBB3sBBB72s72sH"
    raw_fields = struct.unpack_from(fmt, msg, offset)
    fields = {}
    fields['snr_carriers'] = raw_fields[0]
    fields['phase_diff'] = raw_fields[1]
    try:
        fields['mod_type'] = G3C.G3_PHY_MODTYPE[raw_fields[2]]
    except KeyError:
        logging.error(f"Unknown modulation type: {raw_fields[2]}")
    try:
        fields['mod_scheme'] = G3C.G3_PHY_MODSCHEME[raw_fields[3]]
    except KeyError:
        logging.error(f"Unknown modulation scheme: {raw_fields[3]}")
    fields['tonemap'] = raw_fields[4]
    try:
        fields['dt'] = G3C.G3_PHY_DT[raw_fields[5]]
    except KeyError:
        logging.error(f"Unknown dt: {raw_fields[5]}")
    try:
        fields['rs_blocks'] = G3C.G3_PHY_RSBLOCKS[raw_fields[6]]
    except KeyError:
        logging.error(f"Unknown rs blocks: {raw_fields[6]}")
    fields['lqi'] = raw_fields[7]
    fields['noise_power'] = raw_fields[8]
    fields['signal_power'] = raw_fields[9]
    fields['len'] = raw_fields[10]
    offset = offset + struct.calcsize(fmt)
    fields['payload'] = msg[offset:]
    return fields

# Table 104. pg 73
def decode_phy_ack(msg, offset):
    fmt = "HBB"
    raw_fields = struct.unpack_from(fmt, msg, offset)
    fields = {}
    fields['fcs'] = raw_fields[0]
    fields['dt_ssca'] = raw_fields[1]
    fields['crc5_8'] = raw_fields[2]
    return fields

# Table 107, pg 74
def decode_phy_rf(msg, offset):
    fmt = "BBH"
    raw_fields = struct.unpack_from(fmt, msg, offset)
    fields = {}
    fields['rssi'] = raw_fields[0]
    fields['noise'] = raw_fields[1]
    fields['len'] = raw_fields[2]
    offset = offset + struct.calcsize(fmt)
    fields['payload'] = msg[offset:]
    return fields

def decode_unknown(msg, offset):
    fields = {}
    fields['payload'] = msg[offset:]
    logging.error(f"Invalid sniffer frame type; data: {fields['payload']}")
    return fields

G3LIB_SNIFFER_DECODER = {
    0x00: decode_phy_data,
    0x01: decode_phy_ack,
    0x02: decode_mac_beacon,
    0x03: decode_mac_data,
    0x04: decode_mac_cmd,
    0x05: decode_phy_rf,
    0x06: decode_mac_rf_ack,
    0xFF: decode_unknown
}

# Datasheet pg 62
class G3SnifferInd(G3Resp):
    g3_id = 0x2b
    g3_name = 'G3LIB-SNIFFER'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BIH", msg['data'], 1)
        self.raw_fields = list(raw_fields)
        self.fields['timestamp'] = raw_fields[1]
        self.fields['length'] = raw_fields[2]
        try:
            self.fields['frametype'] = G3C.G3LIB_SNIFFER_FRAMETYPE[raw_fields[0]]
            self.fields['data'] = G3LIB_SNIFFER_DECODER[raw_fields[0]](msg['data'], 8)
        except KeyError:
            logging.error(f"Unknown sniffer frame type key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 72
class G3PhyData(G3Resp):
    g3_id = 0x41
    g3_name = 'G3PHY-DATA'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BBBBB", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['cs_threshold_ev'] = raw_fields[1]
        self.fields['tx_pwr_begin'] = raw_fields[2]
        self.fields['tx_pwr_end'] = raw_fields[3]
        self.fields['thermal_warning'] = raw_fields[4]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 72
class G3PhyDataInd(G3Resp):
    g3_id = 0x42
    g3_name = 'G3PHY-DATA.Ind'

    def decode(self, msg):
        super().decode(msg)
        self.fields = decode_phy_data(msg['data'], 1)

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 73
class G3PhyAck(G3Resp):
    g3_id = 0x44
    g3_name = 'G3PHY-ACK'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 73
class G3PhyAckInd(G3Resp):
    g3_id = 0x45
    g3_name = 'G3PHY-ACK.Ind'

    def decode(self, msg):
        super().decode(msg)
        self.fields = decode_phy_ack(msg['data'], 1)

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 74
class G3PhyRf(G3Resp):
    g3_id = 0x47
    g3_name = 'G3PHY-RF'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 74
class G3PhyRfInd(G3Resp):
    g3_id = 0x48
    g3_name = 'G3PHY-RF.Ind'

    def decode(self, msg):
        super().decode(msg)
        self.fields = decode_phy_rf(msg['data'], 1)

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 87
class BootSrvStartResp(G3Resp):
    g3_id = 0xB1
    g3_name = 'G3BOOT-SRV-START'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 88
class BootSrvJoinInd(G3Resp):
    g3_id = 0xB7
    g3_name = 'G3BOOT-SRV-JOIN'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<QH", msg['data'], 1)
        self.raw_fields = raw_fields
        self.fields['e_addr'] = raw_fields[0]
        self.fields['short_id'] = raw_fields[1]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 90
class BootDevStartResp(G3Resp):
    g3_id = 0xB9
    g3_name = 'G3BOOT-DEV-START'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BHH", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['short_id'] = raw_fields[1]
        self.fields['pan_id'] = raw_fields[2]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 90
class BootDevPANSortInd(G3Resp):
    g3_id = 0xC1
    g3_name = 'G3BOOT-DEV-PANSORT.I'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = list(raw_fields)
        self.fields['pan_count'] = raw_fields[0]
        offset = 2 # first byte was the error code, second the PAN count
        self.fields['pan'] = []
        for _ in range(0, self.fields['pan_count']):
            raw_fields = G3S.unpack_PAN_descriptor(msg['data'][offset:])
            self.raw_fields.append(raw_fields)
            self.fields['pan'].append(raw_fields)
            offset = offset + 8 # PAN descriptor is 8 bytes

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 89
class BootGetPSKInd(G3Resp):
    g3_id = 0xC4
    g3_name = 'G3BOOT-SRV-GETPSK'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<QB36s", msg['data'], 1)
        self.raw_fields = raw_fields
        self.fields['e_addr'] = raw_fields[0]
        self.fields['idp_len'] = raw_fields[1]
        if not 1 <= self.fields['idp_len'] <= 36:
            logging.warning("IDP length out of range")
        self.fields['idp'] = raw_fields[:self.fields['idp_len']]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 89
class BootSrvSetPSKResp(G3Resp):
    g3_id = 0xC6
    g3_name = 'G3BOOT-SRV-SETPSK'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 91
class UDPData(G3Resp):
    g3_id = 0xd1
    g3_name = 'G3UDP-DATA'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BBB", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['handle'] = raw_fields[1]
        self.fields['nexthop_medium'] = raw_fields[2]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 92
class UDPDataInd(G3Resp):
    g3_id = 0xd2
    g3_name = 'G3UDP-DATA.Ind'

    def decode(self, msg):
        super().decode(msg)
        fmt = "<BH"
        offset = 1
        raw_fields = struct.unpack_from(fmt, msg['data'], offset)
        offset = offset + struct.calcsize(fmt)
        self.fields['prevhop_addrmode'] = raw_fields[0]
        self.fields['prevhop_pan'] = raw_fields[1]
        if self.fields['prevhop_addrmode'] == 0:
            fmt = "<"
        elif self.fields['prevhop_addrmode'] == 2:
            fmt = "<H"
        elif self.fields['prevhop_addrmode'] == 3:
            fmt = "<Q"
        else:
            logging.error(f"Unknown prevhop_addrmode {self.fields['prevhop_addrmode']}")
            return
        fmt = fmt + "BBBB3sB"
        raw_fields = struct.unpack_from(fmt, msg['data'], offset)
        offset = offset + struct.calcsize(fmt)
        o = 0
        if self.fields['prevhop_addrmode'] != 0:
            o = 1
            self.fields['prevhop_addr'] = raw_fields[0]
        self.fields['lqi'] = raw_fields[0+o]
        self.fields['phasediff'] = raw_fields[1+o]
        try:
            self.fields['modtype'] = G3C.G3_PHY_MODTYPE[raw_fields[2+o]]
        except KeyError:
            logging.error(f"Unknown modulation type: {raw_fields[2]}")
        try:
            self.fields['modscheme'] = G3C.G3_PHY_MODSCHEME[raw_fields[3+o]]
        except KeyError:
            logging.error(f"Unknown modulation scheme: {raw_fields[3]}")
        self.fields['tonemap'] = raw_fields[4+o]
        self.fields['bc0num'] = int(raw_fields[5+o])
        bc0num = self.fields['bc0num']
        if bc0num > 6:
            logging.error(f"bc0num is over maximum: {bc0num}")
            return
        fmt = f"<{bc0num}BBB16sH16sHH"
        raw_fields = struct.unpack_from(fmt, msg['data'], offset)
        offset = offset + struct.calcsize(fmt)
        self.fields['bc0'] = []
        for i in range(0, bc0num):
            self.fields['bc0'].append(raw_fields[i])
        self.fields['prevhop_media'] = raw_fields[0+bc0num]
        self.fields['conn_id'] = raw_fields[1+bc0num]
        self.fields['src_addr'] = raw_fields[2+bc0num]
        self.fields['src_port'] = raw_fields[3+bc0num]
        self.fields['dest_addr'] = raw_fields[4+bc0num]
        self.fields['dest_port'] = raw_fields[5+bc0num]
        self.fields['data_len'] = raw_fields[6+bc0num]
        self.fields['data'] = msg['data'][offset:]
        if self.fields['data_len'] != len(self.fields['data']):
            logging.error(f"UDP packet recived, len != len(data); len: {self.fields['data_len']}, len(data): {len(self.fields['data'])}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 92
class UDPConnSet(G3Resp):
    g3_id = 0xd4
    g3_name = 'G3UDP-CONN-SET'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 92
class UDPConnGet(G3Resp):
    g3_id = 0xd6
    g3_name = 'G3UDP-CONN-GET'

    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BB16sHH", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['conn_id'] = raw_fields[1]
        self.fields['remote_addr'] = raw_fields[2]
        self.fields['remote_port'] = raw_fields[3]
        self.fields['local_port'] = raw_fields[4]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 93
class G3EchoResp(G3Resp):
    g3_id = 0xd8
    g3_name = 'G3ICMP-ECHO'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<BBB", msg['data'], 1)
        self.raw_fields = raw_fields
        try:
            self.fields['status'] = G3C.G3_RESULTS[raw_fields[0]]
        except KeyError:
            logging.error(f"Unknown status key on {self.g3_name}: {raw_fields[0]}")
        self.fields['handle'] = raw_fields[1]
        self.fields['nexthop_medium'] = raw_fields[2]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

# Datasheet pg 93
def decode_echo(msg, offset):
    fmt = "<BH"
    raw_fields = struct.unpack_from(fmt, msg['data'], offset)
    fields = {}
    offset = offset + struct.calcsize(fmt)
    fields['prevhop_addrmode'] = raw_fields[0]
    fields['prevhop_pan'] = raw_fields[1]
    if fields['prevhop_addrmode'] == 0:
        fmt = "<"
    elif fields['prevhop_addrmode'] == 2:
        fmt = "<H"
    elif fields['prevhop_addrmode'] == 3:
        fmt = "<Q"
    else:
        logging.error(f"Unknown prevhop_addrmode {fields['prevhop_addrmode']}")
        return fields
    fmt = fmt + "BBBB3sB"
    raw_fields = struct.unpack_from(fmt, msg['data'], offset)
    offset = offset + struct.calcsize(fmt)
    o = 0
    if fields['prevhop_addrmode'] != 0:
        o = 1
        fields['prevhop_addr'] = raw_fields[0]
    fields['lqi'] = raw_fields[0+o]
    fields['phasediff'] = raw_fields[1+o]
    try:
        fields['modtype'] = G3C.G3_PHY_MODTYPE[raw_fields[2+o]]
    except KeyError:
        logging.error(f"Unknown modulation type: {raw_fields[2]}")
    try:
        fields['modscheme'] = G3C.G3_PHY_MODSCHEME[raw_fields[3+o]]
    except KeyError:
        logging.error(f"Unknown modulation scheme: {raw_fields[3]}")
    fields['tonemap'] = raw_fields[4+o]
    fields['bc0num'] = int(raw_fields[5+o])
    bc0num = fields['bc0num']
    if bc0num > 6:
        logging.error(f"bc0num is over maximum: {bc0num}")
        return fields
    fmt = f"<{bc0num}BB16sH"
    raw_fields = struct.unpack_from(fmt, msg['data'], offset)
    offset = offset + struct.calcsize(fmt)
    fields['bc0'] = []
    for i in range(0, bc0num):
        fields['bc0'].append(raw_fields[i])
    fields['prevhop_media'] = raw_fields[0+bc0num]
    fields['src_addr'] = raw_fields[1+bc0num]
    fields['data_len'] = raw_fields[2+bc0num]
    fields['data'] = msg[offset:]
    return fields

class G3EchoRepInd(G3Resp):
    g3_id = 0xd9
    g3_name = 'G3ICMP-ECHOREP'
    def decode(self, msg):
        super().decode(msg)
        self.fields = decode_echo(msg['data'], 1)

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

class G3EchoReqInd(G3Resp):
    g3_id = 0xdf
    g3_name = 'G3ICMP-ECHOREQ'
    def decode(self, msg):
        super().decode(msg)
        self.fields = decode_echo(msg['data'], 1)

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')

class MetaError(G3Resp):
    g3_id = 0xFD
    g3_name = 'META-ERROR'
    def decode(self, msg):
        pass

    def pr_decode(self):
        pass
