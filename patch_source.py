# SPDX-License-Identifier: MIT
"""Original authored Thumb payloads. No copied Ultimate2/2C firmware code.
The patch recipe contains preimages/branches; these routines independently
reassemble and verify all four injected payloads in the final normal image.
"""
import struct
BASE=0x01018000;ENTRY=0x0101e9e4;STUB=0x01031900
START=0x01031a00;ARM=0x01031a60;ACTIVITY=0x01031ac0
TIMER=0x2441c;CONTEXT=TIMER+12;TICK=0x2054c
def bl(at,target):
    d=target-at-4
    assert d%2==0 and -(1<<22)<=d<(1<<22)
    return struct.pack('<HH',0xf000|((d>>12)&0x7ff),0xf800|((d>>1)&0x7ff))


class Assemble:
    def __init__(self,base):self.base=base;self.b=bytearray();self.labels={};self.fix=[]
    def emit(self,*words):
        for word in words:self.b+=struct.pack('<H',word)
    def label(self,name):self.labels[name]=self.base+len(self.b)
    def branch(self,op,name):self.fix.append(('b',len(self.b),op,name));self.emit(0)
    def load(self,register,name):self.fix.append(('ldr',len(self.b),register,name));self.emit(0)
    def call(self,target):self.b+=bl(self.base+len(self.b),target)
    def literal(self,name,value):
        while len(self.b)%4:self.emit(0xbf00)
        self.label(name);self.b+=struct.pack('<I',value)
    def finish(self):
        for kind,offset,arg,label in self.fix:
            at=self.base+offset;target=self.labels[label]
            if kind=='b':
                delta=(target-at-4)//2
                if arg==0xe000:
                    assert -1024<=delta<=1023
                    value=arg|(delta&0x7ff)
                else:
                    assert -128<=delta<=127
                    value=arg|(delta&255)
            else:
                delta=target-((at+4)&~3);assert delta%4==0 and 0<=delta<=1020
                value=0x4800|(arg<<8)|(delta//4)
            struct.pack_into('<H',self.b,offset,value)
        return bytes(self.b)


def assemble():
    a=Assemble(STUB)
    a.emit(0xb5f8,0x4604)                 # preserve r3-r7,lr; requested ->r4
    a.emit(0x2c02);a.branch(0xd000,'fast') # restore a saved2ms interval safely
    a.load(0,'mode');a.emit(0x7800,0x2801)
    a.branch(0xd100,'normal')
    a.emit(0x2c05);a.branch(0xd000,'fast')
    a.emit(0x2c0a);a.branch(0xd100,'normal')
    a.label('fast');a.emit(0x2402,0x2601,0x25fa,0x006d)  # p2, scale1, divisor500
    a.branch(0xe000,'clock')
    a.label('normal');a.emit(0x2105,0x4620);a.call(0x01018240)
    a.emit(0xb2c6,0x25c8)                 # exact old uint8(p/5), divisor200
    a.label('clock');a.load(0,'clockbase');a.emit(0x6a00,0x0700,0x0f00,0x1c81)
    a.load(0,'crystal');a.call(0x01018240)
    a.emit(0x4629);a.call(0x01018240);a.emit(0x4370);a.call(0x01028138)
    a.load(0,'period');a.emit(0x7801,0x7004,0x42a1)
    a.branch(0xd000,'done')
    a.call(0x0102a364)                    # recompute activity timeout AFTER period changes
    a.label('done');a.emit(0xbdf8)
    code_end=STUB+len(a.b)
    a.literal('mode',0x201aa);a.literal('clockbase',0xf8540)
    a.literal('crystal',192000000);a.literal('period',0x20265)
    return a.finish(),code_end


def start_code():
    a=Assemble(START)
    a.emit(0xb510,0x4604)  # original callback prologue
    # Capture on every entry: RF/period may change while the callback is running.
    a.load(1,'tick');a.emit(0x6809);a.load(2,'context');a.emit(0x6011)
    a.call(0x010285f8)
    # Original body ends with its original pop{r4,pc}; saved LR still belongs to caller.
    a.call(0x0101daec)
    a.literal('tick',TICK);a.literal('context',CONTEXT)
    return a.finish()


def arm_code():
    a=Assemble(ARM)
    a.emit(0xb510)
    a.load(2,'timer');a.emit(0x4290);a.branch(0xd100,'fallback')
    a.emit(0x2900);a.branch(0xd100,'fallback')
    a.load(2,'rf');a.emit(0x7812,0x2a01);a.branch(0xd100,'fallback')
    a.load(2,'period');a.emit(0x7812,0x2a02);a.branch(0xd100,'fallback')
    a.load(2,'context');a.emit(0x6812,0x3201,0x6042,0xbd10)
    a.label('fallback');a.call(0x0102bcf0);a.emit(0xbd10)
    a.literal('timer',TIMER);a.literal('rf',0x201aa)
    a.literal('period',0x20265);a.literal('context',CONTEXT)
    return a.finish()


def activity_code():
    a=Assemble(ACTIVITY)
    a.emit(0xb510);a.call(0x01023f1c)
    a.emit(0x2800);a.branch(0xd100,'done')
    a.load(0,'changed_axes');a.emit(0x6800,0x2100,0x43c9,0x4288)
    a.branch(0xd000,'zero')
    a.emit(0x2204)
    a.label('axis');a.emit(0xb2c1,0x2977);a.branch(0xd300,'active')
    a.emit(0x2987);a.branch(0xd800,'active')
    a.emit(0x0a00,0x3a01,0x2a00);a.branch(0xd100,'axis')
    a.label('zero');a.emit(0x2000);a.branch(0xe000,'done')
    a.label('active');a.emit(0x2001)
    a.label('done');a.emit(0xbd10)
    a.literal('changed_axes',0x20238)
    return a.finish()

def verify_payloads(image):
    for address, code in ((STUB,assemble()[0]),(START,start_code()),(ARM,arm_code()),(ACTIVITY,activity_code())):
        if image[address-BASE:address-BASE+len(code)] != code:
            raise ValueError(f'Authored payload mismatch at {address:#x}')
