

def pauls_decorator(func):

    def decorator(*args):
        print('boop', args
        return func()

    return decorator

@pauls_decorator
def fooboo(*args):
    print('woop', sum(args)

fooboo(1, 2, 3)


#
#
#
#
# import casperfpga
# import struct
#
# for host in ['roach02095e','roach020960','roach020a0b','roach020927','roach020919','roach020925','roach02091a','roach020923']:
#
#
#
#
# f = casperfpga.KatcpFpga('roach020923')
# # f = casperfpga.KatcpFpga('roach02095e')
# f.get_system_information()
#
# not_done = True
# attctr = 0
#
# mem_depth = 1024
#
# def par_check(num, bits):
#     par = 0
#     for bitct in range(0, bits):
#         thisbit = (num >> bitct) & 0x01
#         par ^= thisbit
#     par2 = len(bin(num).replace('0b', '').replace('0', '')) % 2
#     if par2 != par:
#         print(''
#         print(num, bin(num), len(bin(num)), bits, par, par2
#         raise RuntimeError
#     return par
#
# print(4, par_check(4, 64)
# print(5, par_check(5, 64)
#
# # 'bram_qdr0' 'qdr0_memory'
#
# # # qdr
# # for ctr in range(0, mem_depth):
# #     d = f.read('qdr0_memory', 8, ctr*8)
# #     num = struct.unpack('>2L', d)
# #     num_0 = num[0]
# #     num_1 = num[1]
# #     num = (num[1] << 32) | num[0]
# #     for foo in range(0, 5):
# #         d2 = f.read('qdr0_memory', 8, ctr*8)
# #         #num2 = struct.unpack('>Q', d2)[0]
# #         num2 = struct.unpack('>2L', d)
# #         num2 = (num2[1] << 32) | num2[0]
# #         assert num2 == num
# #     num_masked = num & ((2**60)-1)
# #     print(ctr, num, num_masked, par_check(num, 63), bin(num_0), bin(num_1)
#
# # # bram
# # for ctr in range(0, mem_depth):
# #     d = f.read('bram_qdr0', 8, ctr*8)
# #     num = struct.unpack('>Q', d)[0]
# #     for foo in range(0, 5):
# #         d2 = f.read('bram_qdr0', 8, ctr*8)
# #         num2 = struct.unpack('>Q', d2)[0]
# #         assert num2 == num
# #     num_masked = num & ((2**63)-1)
# #     print(ctr, num, num_masked, len(bin(num)), par_check(num, 64)
#
# attctr = 0
#
# import time
#
# while True:
#
#     time.sleep(0.1)
#
#     print('attempt %i' % attctr
#
#     d = f.snapshots.sys3_vacc0_qv_sv_ss.read(man_trig=True)['data']
#
#     for ctr in range(0, len(d['dv'])):
#
#         dataword = (d['datamid'][ctr] << 32) | d['datalsb'][ctr]
#         parbit = dataword >> 63
#
#         for key in d.keys():
#             print('%s(%i)' % (key, d[key][ctr]),
#
#         softparerr = par_check(dataword, 64)
#
#         print('dataword(%i) softERR(%i) parbit(%i)' % (dataword, softparerr, parbit),
#
#         print(''
#
#         # if d['datamsb'][ctr] == 128:
#         #     assert softparerr == 0
#         #     assert d['parerr'][ctr] == 1
#         # else:
#         #     assert d['datamsb'][ctr] == 0
#         #     assert softparerr == d['parerr'][ctr]
#         #     assert softparerr == 0
#
#         assert d['datamsb'][ctr] == 0
#         assert softparerr == d['parerr'][ctr]
#         assert softparerr == 0
#
#
#         # if d['parerr'][ctr] == 1 and d['dv'][ctr] == 0:
#         #     raise RuntimeError
#
#
#
#
#
#         attctr += 1
#
#
# # while not_done:
# #     print('attempt', attctr
# #     d = f.snapshots.sys3_vacc0_qv_sv2_ss.read(man_trig=True, man_valid=True)['data']
# #     for ctr in range(0, len(d[d.keys()[0]])):
# #         if d['parerr'][ctr] == 1:
# #             not_done = False
# #             print('got a parity error'
# #     attctr += 1
# #
# # raw = f.read('sys3_vacc0_qv_sv2_ss_bram', 32768)
# #
# # raw_bytes = struct.unpack('>32768B', raw)
# #
# # for byte in range(0, len(raw_bytes), 16):
# #     # for bytectr in range(0, 16):
# #     #     print(raw_bytes[byte + bytectr],
# #     # print(''
# #     parerr = raw_bytes[byte + 15] & 0b1
# #     dv = (raw_bytes[byte + 15] >> 1) & 0b1
# #     address = (raw_bytes[byte + 15] >> 2) & 0b111111
# #     address |= raw_bytes[byte + 14] & 0b1111111
# #
# #     data = (raw_bytes[byte + 14] >> 7) & 0b1
# #     data |= raw_bytes[byte + 13] << 1
# #     data |= raw_bytes[byte + 12] << 9
# #     data |= raw_bytes[byte + 11] << 17
# #     data |= raw_bytes[byte + 10] << 25
# #     data |= raw_bytes[byte + 9] << 33
# #     data |= raw_bytes[byte + 8] << 41
# #     data |= raw_bytes[byte + 7] << 49
# #     data |= raw_bytes[byte + 6] << 57
# #
# #     print(parerr, dv, address, data
