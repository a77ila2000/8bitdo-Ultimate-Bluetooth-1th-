# SPDX-License-Identifier: MIT
"""Bounded Windows boot identity queries. Does not read serials, keys, pairing or calibration."""
import ctypes as c
from ctypes import wintypes as w
import json,struct,uuid
INVALID=c.c_void_p(-1).value
setup=c.WinDLL('setupapi',use_last_error=True)
kernel=c.WinDLL('kernel32',use_last_error=True)


class GUID(c.Structure):
    _fields_=[('a',c.c_uint32),('b',c.c_uint16),('d',c.c_uint16),('e',c.c_ubyte*8)]


class Interface(c.Structure):
    _fields_=[('size',w.DWORD),('guid',GUID),('flags',w.DWORD),('reserved',c.c_void_p)]


setup.SetupDiGetClassDevsW.argtypes=[c.POINTER(GUID),w.LPCWSTR,w.HWND,w.DWORD]
setup.SetupDiGetClassDevsW.restype=w.HANDLE
setup.SetupDiEnumDeviceInterfaces.argtypes=[w.HANDLE,c.c_void_p,c.POINTER(GUID),w.DWORD,c.POINTER(Interface)]
setup.SetupDiEnumDeviceInterfaces.restype=w.BOOL
setup.SetupDiGetDeviceInterfaceDetailW.argtypes=[w.HANDLE,c.POINTER(Interface),c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p]
setup.SetupDiGetDeviceInterfaceDetailW.restype=w.BOOL
setup.SetupDiDestroyDeviceInfoList.argtypes=[w.HANDLE]
kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
kernel.CreateFileW.restype=w.HANDLE
kernel.CloseHandle.argtypes=[w.HANDLE]
kernel.DeviceIoControl.argtypes=[w.HANDLE,w.DWORD,c.c_void_p,w.DWORD,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p]
kernel.DeviceIoControl.restype=w.BOOL


k=kernel;s=setup
hid=c.WinDLL("hid",use_last_error=True)

class OVERLAPPED(c.Structure):
    _fields_=[('internal',c.c_size_t),('internal_high',c.c_size_t),('offset',w.DWORD),
              ('offset_high',w.DWORD),('event',w.HANDLE)]


k.CreateEventW.argtypes=[c.c_void_p,w.BOOL,w.BOOL,w.LPCWSTR];k.CreateEventW.restype=w.HANDLE
k.WriteFile.argtypes=[w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.POINTER(OVERLAPPED)]
k.ReadFile.argtypes=k.WriteFile.argtypes
k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.WaitForSingleObject.restype=w.DWORD
k.GetOverlappedResult.argtypes=[w.HANDLE,c.POINTER(OVERLAPPED),c.POINTER(w.DWORD),w.BOOL]
k.CancelIoEx.argtypes=[w.HANDLE,c.POINTER(OVERLAPPED)]
hid.HidD_GetPreparsedData.argtypes=[w.HANDLE,c.POINTER(c.c_void_p)]
hid.HidP_GetCaps.argtypes=[c.c_void_p,c.c_void_p];hid.HidP_GetCaps.restype=c.c_long
hid.HidD_FreePreparsedData.argtypes=[c.c_void_p]


def interfaces():
    guid=GUID.from_buffer_copy(uuid.UUID('4d1e55b2-f16f-11cf-88cb-001111000030').bytes_le)
    info=s.SetupDiGetClassDevsW(c.byref(guid),None,None,0x12)
    if info==INVALID:raise c.WinError(c.get_last_error())
    try:
        for index in range(512):
            entry=Interface();entry.size=c.sizeof(entry)
            if not s.SetupDiEnumDeviceInterfaces(info,None,c.byref(guid),index,c.byref(entry)):
                if c.get_last_error()==259:return
                raise c.WinError(c.get_last_error())
            needed=w.DWORD()
            s.SetupDiGetDeviceInterfaceDetailW(info,c.byref(entry),None,0,c.byref(needed),None)
            if not 8<=needed.value<=65536:raise ValueError('Interface length')
            buf=c.create_string_buffer(needed.value);struct.pack_into('<I',buf,0,8 if c.sizeof(c.c_void_p)==8 else 6)
            if not s.SetupDiGetDeviceInterfaceDetailW(info,c.byref(entry),buf,len(buf),c.byref(needed),None):raise c.WinError(c.get_last_error())
            path=c.wstring_at(c.addressof(buf)+4)
            if 'vid_2dc8&pid_3208' in path.lower():yield path
    finally:s.SetupDiDestroyDeviceInfoList(info)


def io(handle,data=None):
    buf=c.create_string_buffer(data,65) if data is not None else c.create_string_buffer(65)
    event=k.CreateEventW(None,True,False,None)
    if not event:raise c.WinError(c.get_last_error())
    ov=OVERLAPPED();ov.event=event;done=w.DWORD()
    try:
        function=k.WriteFile if data is not None else k.ReadFile
        success=function(handle,buf,65,c.byref(done),c.byref(ov))
        if not success:
            error=c.get_last_error()
            if error!=997:raise c.WinError(error)
            if k.WaitForSingleObject(event,3000)!=0:
                k.CancelIoEx(handle,c.byref(ov))
                # Wait for cancellation completion before releasing the kernel's buffers.
                k.GetOverlappedResult(handle,c.byref(ov),c.byref(done),True)
                raise TimeoutError('HID request timed out; operation cancelled')
            if not k.GetOverlappedResult(handle,c.byref(ov),c.byref(done),False):raise c.WinError(c.get_last_error())
        if done.value!=65:raise ValueError(f'Unexpected HID length{done.value}')
        return buf.raw[1:65]
    finally:k.CloseHandle(event)


def crc16(data):
    crc=65535
    for value in data:
        crc^=value
        for _ in range(8):crc=(crc>>1)^0xa001 if crc&1 else crc>>1
    return crc


def command(handle,cmd,address=0,length=4):
    if (cmd,address,length) not in ((8,0,4),(5,0x01017040,8)):
        raise ValueError('Only identity and fixed version read permitted')
    packet=bytearray(64);packet[0]=5
    struct.pack_into('<H',packet,1,cmd)
    struct.pack_into('<HHII',packet,5,length,0 if cmd==8 else crc16(bytes(length)),0 if cmd==8 else length,address)
    io(handle,b'\0'+packet)
    for _ in range(3):
        reply=io(handle)
        if reply[:2]!=b'\0\x05' or int.from_bytes(reply[4:6],'little')!=cmd:continue
        if int.from_bytes(reply[2:4],'little')!=0:raise ValueError('Bootloader rejected query')
        n,checksum,total,offset=struct.unpack_from('<HHII',reply,6)
        if (n,total,offset)!=(length,length,address):raise ValueError('Identity response header mismatch')
        data=reply[18:18+n]
        if crc16(data)!=checksum:raise ValueError('Identity response CRC mismatch')
        return data
    raise ValueError('No matching identity response')



def identify(target):
    paths=list(interfaces())
    if len(paths)!=1:raise ValueError(f'Exactly one3208 HID interface required; found{len(paths)}')
    handle=k.CreateFileW(paths[0],0xc0000000,3,None,3,0x40000000,None)
    if handle==INVALID:raise c.WinError(c.get_last_error())
    try:
        preparsed=c.c_void_p()
        if not hid.HidD_GetPreparsedData(handle,c.byref(preparsed)):raise c.WinError(c.get_last_error())
        try:
            caps=c.create_string_buffer(64)
            if hid.HidP_GetCaps(preparsed,caps)!=0x110000:raise ValueError('Cannot read HID caps')
            usage,page,input_size,output_size=struct.unpack_from('<4H',caps)
            if (input_size,output_size)!=(65,65):raise ValueError(f'Unrecognized HID report lengths{input_size}/{output_size}')
        finally:hid.HidD_FreePreparsedData(preparsed)
        identity=command(handle,8)
        expected = 0x6007 if target == 'controller' else 0x6008
        if identity != struct.pack('<I', expected): raise ValueError('Boot firmware type does not match selected target')
        if target == 'receiver': return {'verified_pid':hex(expected),'scope':'Read-only command8 identity; no flash/erase'}
        version=command(handle,5,0x01017040,8)
        result=dict(verified_controller_pid='0x6007',identity_hex=identity.hex(),version_record_hex=version.hex(),
                    main_version=struct.unpack_from('<H',version)[0],beta=struct.unpack_from('<H',version,4)[0],
                    scope='Boot command8 identity and command5 fixed version read only')
        if result['main_version'] != 111: raise ValueError('Install exact official controller v1.11 first')
        return result
    finally:k.CloseHandle(handle)
