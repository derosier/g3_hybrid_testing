import struct

# Table 126. Pan Descriptor structure. pg. 81
def unpack_PAN_descriptor(data):
    # We use unpack_from because there might be data after this area, only unpack
    # what we need but from the front.
    raw = struct.unpack_from("<HBHHB", data, 0)
    fields = {}
    fields['PAN_ID'] = raw[0]
    fields['link_quality'] = raw[1]
    fields['LBA_addr'] = raw[2]
    fields['route_cost'] = raw[3]
    fields['media_type'] = raw[4]
    return fields

def pack_PAN_descriptor(fields):
    data = struct.pack("<HBHHB", fields['PAN_ID'], fields['link_quality'],
                                 fields['LBA_addr'], fields['route_cost'], fields['media_type'])
    return data

RF_CFG = "<IBIIIBI18B"
