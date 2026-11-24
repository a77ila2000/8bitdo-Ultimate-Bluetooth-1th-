"""Offline receiver descriptor experiment. Never opens hardware or vendor DLLs."""
from pathlib import Path
import binascii
import hashlib
import json
import struct

STOCK_SHA='099101a6ca62321b76de2b7c61452342be794956a622aba542120125d91ffb97'
APP_SHA='a21c0fa6e0d35fe0933dbc4cc95f9cd789f6db2b8c7c29c7b3b23c67e1e874da'
APP_BASE=0x4000
APP_INTERVAL_OFFSET=0x10ee4
ENTRY=struct.Struct('<HHIIBBH16s')


def sha(data):return hashlib.sha256(data).hexdigest()
def crc(data):return binascii.crc_hqx(data,0)


def enc(data,key=0xffff):
    out=bytearray(data)
    for index in range(len(out)):
        out[index]^=key&255
        key=((key<<1)^(0x1021 if key&0x8000 else 0))&65535
    return bytes(out)


def sfc(data,key):
    out=bytearray(data)
    for offset in range(0,len(data),32):
        out[offset:offset+32]=enc(data[offset:offset+32],key^(offset>>2))
    return bytes(out)


def entry(data,offset):
    chunk=data[offset:offset+32]
    assert len(chunk)==32 and crc(chunk[2:])==int.from_bytes(chunk[:2],'little'), ('header CRC',hex(offset))
    hcrc,dcrc,pos,size,flags,reserved,last,name=ENTRY.unpack(chunk)
    return dict(header_offset=offset,header_crc=hcrc,data_crc=dcrc,offset=pos,size=size,
                flags=flags,reserved=reserved,last=last,name=name.split(b'\0',1)[0].decode('ascii'))


def verify(raw):
    assert len(raw)>=28
    version,address,length,pid,*reserved=struct.unpack('<7I',raw[:28])
    assert 101<=version<=104 and address==0x3000 and pid==0x6008 and reserved==[0,0,0]
    assert length==len(raw)-28 and length in (0x40000,0x43000)
    payload=raw[28:]
    flash_header=enc(payload[:32])
    assert crc(flash_header[2:])==int.from_bytes(flash_header[:2],'little')
    assert payload[4:8]==b'2DC8' and payload[16:22]==b'80NA_R'
    top=[]
    for offset in range(32,32*32,32):
        decoded=enc(payload[offset:offset+32])
        item=entry(decoded,0);item['header_offset']=offset;top.append(item)
        if item['last']:break
    assert [i['name']for i in top]==['uboot.boot','isd_config.ini','app_dir_head','key_mac']
    boot=top[0]
    boot_encoded=payload[boot['offset']:boot['offset']+boot['size']]
    boot_plain=bytearray(boot_encoded)
    count=struct.unpack_from('<H',enc(boot_encoded[:16]))[0]
    assert 1<=count<=16
    banks=[]
    for index in range(count):
        h=enc(boot_encoded[index*16:index*16+16])
        assert crc(h[:14])==int.from_bytes(h[14:16],'little')
        bank_id,size,load,position,data_crc=struct.unpack_from('<HHIIH',h)
        assert position+size<=len(boot_encoded)
        body=enc(boot_encoded[position:position+size])
        assert crc(body)==data_crc
        boot_plain[index*16:index*16+16]=h
        boot_plain[position:position+size]=body
        banks.append(dict(index=index,size=size,load=hex(load),data_crc=hex(data_crc)))
    assert crc(boot_plain)==boot['data_crc']
    config=top[1]
    configuration=payload[config['offset']:config['offset']+config['size']]
    assert crc(configuration)==config['data_crc'] and len(configuration)>=34
    encoded_key=configuration[:32]
    assert crc(encoded_key)==int.from_bytes(configuration[32:34],'little')
    threshold=sum(encoded_key[:16])&255
    threshold=0xaa if threshold>=0xe0 else 0x55 if threshold<=0x10 else threshold
    key=sum(1<<i for i in range(16) if encoded_key[16+i]^encoded_key[15-i]<threshold)
    assert key==0x2f1b and top[2]['offset']==APP_BASE and top[2]['flags']==0x81
    assert top[2]['data_crc']==0xffff and top[2]['size']==0xffffffff
    assert top[3]['flags']&0x10 and top[3]['offset']==0x7f000
    decoded=sfc(payload[APP_BASE:],key)
    assert sfc(decoded,key)==payload[APP_BASE:]
    areas=[];files=[];base=0
    while base+32<=len(decoded):
        area=entry(decoded,base)
        assert area['flags']==0x83 and area['size']>=32 and base+area['size']<=len(decoded)
        assert crc(decoded[base+32:base+area['size']])==area['data_crc'], ('area data CRC',area['name'])
        child_offset=base+32;children=[]
        while child_offset+32<=base+area['size']:
            child=entry(decoded,child_offset);children.append(child)
            if not child['flags']&0x10:
                assert child['flags']==0x82
                position=base+child['offset'];end=position+child['size']
                assert base+32<=position<=end<=base+area['size']
                data=decoded[position:end]
                assert crc(data)==child['data_crc'], ('file data CRC',child['name'])
                files.append(dict(area=area['name'],name=child['name'],position=position,
                                  size=child['size'],sha256=sha(data),header_offset=child_offset))
            if child['last']:break
            child_offset+=32
        area['children']=children;areas.append(area)
        if area['last']:break
        base+=area['size']
    assert [a['name']for a in areas]==['app_area_head','tone']
    app=next(f for f in files if f['name']=='app.bin')
    assert app['position']==0xc0
    return dict(version=version,outer_header=raw[:28].hex(),key=key,top=top,banks=banks,
                areas=areas,files=files,app=app,decoded=decoded)


def update_header(data,offset,data_crc):
    struct.pack_into('<H',data,offset+2,data_crc)
    struct.pack_into('<H',data,offset,crc(data[offset+2:offset+32]))
