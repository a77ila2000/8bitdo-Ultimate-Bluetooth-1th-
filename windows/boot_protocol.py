"""Read-only identity response profiles observed on the two exact device types."""
import struct


def crc16(data):
    crc=65535
    for value in data:
        crc^=value
        for _ in range(8):crc=(crc>>1)^0xa001 if crc&1 else crc>>1
    return crc


def parse_reply(reply,cmd,address,length,target):
    if len(reply)!=64 or reply[:2]!=b'\0\x05' or int.from_bytes(reply[4:6],'little')!=cmd:
        raise ValueError('Identity response framing mismatch')
    if int.from_bytes(reply[2:4],'little')!=0:raise ValueError('Bootloader rejected query')
    n,checksum,total,offset=struct.unpack_from('<HHII',reply,6)
    if n!=length or n>46:raise ValueError('Identity response length mismatch')
    data=reply[18:18+n]
    # Exact receiver CMD8 schema actually observed: PID6008, total0, no CRC.
    # This exception is not permitted for a controller, version read, other PID,
    # nonzero status, address or length. The vendor still validates transfer PID.
    receiver_legacy=(target=='receiver' and cmd==8 and address==0 and length==4 and
                     (total,offset,checksum)==(0,0,0) and data==b'\x08\x60\0\0')
    if not receiver_legacy:
        if (n,total,offset)!=(length,length,address):raise ValueError('Identity response header mismatch')
        if crc16(data)!=checksum:raise ValueError('Identity response CRC mismatch')
    return data
