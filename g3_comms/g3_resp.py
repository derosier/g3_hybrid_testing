import logging
import struct

import g3_comms.g3_consts as G3C

class G3Resp():
    g3_id = 0xFE  # this is not used in the doc
    g3_name = 'UNKNOWN'
    def __init__(self):
        self.callback = None
        self.cb_context = None
        self.raw_msg = b''
        self.raw_fields = b''
        self.fields = {}

    def decode(self, msg):
        self.raw_msg = msg
        self.fields['error_code'] = struct.unpack_from("<B", msg['data'])[0]

    def pr_decode(self):
        logging.debug(f'Msg {self.g3_name} (0x{self.g3_id:02x}): {self.fields}')

    def set_hook(self, callback, context):
        logging.debug(f'{self.g3_name} setting callback to {context}.{callback}')
        self.callback = callback
        self.cb_context = context

    def call_hook(self):
        if self.callback is not None:
            self.callback(self.cb_context, self.g3_name, self.fields)

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
