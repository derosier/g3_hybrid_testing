import pycrc.algorithms

crc16 = pycrc.algorithms.Crc(width = 16, poly = 0x1021,
                             reflect_in = False, xor_in = 0x0,
                             reflect_out = False, xor_out = 0x0)
