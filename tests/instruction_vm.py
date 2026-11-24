# SPDX-License-Identifier: MIT
"""Bounded real-Thumb instruction execution; peripheral work is explicitly hooked.
Unsupported opcodes fail closed. This is not a complete MCU/RF simulator.
"""
import struct
import capstone
from capstone.arm import ARM_OP_IMM, ARM_OP_REG, ARM_OP_MEM
from patch_source import BASE, ENTRY, STUB
VERSIONS={'1.11':(0x101ea90,0x102694c,0x102bde8,0x1026358)}
class ThumbSampler:
 def __init__(self, version, image):
  self.version=version
  self.image=image
  self.entry,self.gpio,self.delay,self.restart=VERSIONS[version]
  self.cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
  self.cs.detail=True
  self.memory={}
  self.write(0x201f7,0,1)
  for n in range(6):self.write(0x2415a+2*n,3000+n*4,2)
 def read(self,a,n):
  if BASE<=a and a+n<=BASE+len(self.image):return int.from_bytes(self.image[a-BASE:a-BASE+n],'little')
  return sum(self.memory.get(a+i,0)<<(8*i) for i in range(n))
 def write(self,a,v,n):
  assert not BASE<=a<BASE+len(self.image),'No flash writes'
  for i in range(n):self.memory[a+i]=(v>>(8*i))&255
 def run(self,raw_samples,channel=4,low=0x880,high=0xfe0):
  self.reg={f'r{i}':0 for i in range(13)}
  self.reg.update(sp=0x2f000,lr=0xdead0001,pc=self.entry,r0=channel,r1=channel+2,r2=low,r3=high)
  it=iter(raw_samples); reads=[]; hooks=[];trace=[];cmp=(0,0); restarted=False
  def val(op):return self.reg[self.cs.reg_name(op.reg)] if op.type==ARM_OP_REG else op.imm&0xffffffff
  def addr(op,pc):
   m=op.mem;name=self.cs.reg_name(m.base)
   b=((pc+4)&~3) if name=='pc' else self.reg[name]
   return b+(self.reg[self.cs.reg_name(m.index)] if m.index else 0)+m.disp
  def signed(v):return v if v<0x80000000 else v-0x100000000
  for step in range(1000):
   pc=self.reg['pc'];i=next(self.cs.disasm(self.image[pc-BASE:pc-BASE+4],pc,count=1),None)
   assert i is not None,hex(pc)
   trace.append(f'{pc:08x} {i.bytes.hex()} {i.mnemonic} {i.op_str}')
   ops=i.operands;m=i.mnemonic;nextpc=pc+i.size
   if m=='push':
    self.reg['sp']-=4*len(ops)
    for n,o in enumerate(ops):self.write(self.reg['sp']+n*4,val(o),4)
   elif m=='pop':
    for n,o in enumerate(ops):self.reg[self.cs.reg_name(o.reg)]=self.read(self.reg['sp']+n*4,4)
    self.reg['sp']+=4*len(ops)
    if any(self.cs.reg_name(o.reg)=='pc' for o in ops):break
   elif m in ('mov','movs'):self.reg[self.cs.reg_name(ops[0].reg)]=val(ops[1])
   elif m in ('sub','adds','add'):
    dst=self.cs.reg_name(ops[0].reg);a=self.reg[dst] if len(ops)==2 else val(ops[1]);b=val(ops[-1])
    self.reg[dst]=(a-b if m=='sub' else a+b)&0xffffffff
   elif m in ('lsls','lsrs'):
    a=val(ops[1]);n=val(ops[2]);self.reg[self.cs.reg_name(ops[0].reg)]=((a<<n) if m=='lsls' else a>>n)&0xffffffff
   elif m=='uxth':self.reg[self.cs.reg_name(ops[0].reg)]=val(ops[1])&0xffff
   elif m=='cmp':cmp=(val(ops[0]),val(ops[1]))
   elif m in ('b','ble','bge','blt'):
    a,b=map(signed,cmp)
    if m=='b' or (m=='ble' and a<=b) or (m=='bge' and a>=b) or (m=='blt' and a<b):nextpc=ops[0].imm
   elif m in ('ldr','ldrb','ldrh'):
    self.reg[self.cs.reg_name(ops[0].reg)]=self.read(addr(ops[1],pc),{'ldr':4,'ldrb':1,'ldrh':2}[m])
   elif m=='strb':self.write(addr(ops[1],pc),val(ops[0]),1)
   elif m=='bl':
    target=ops[0].imm;self.reg['lr']=nextpc|1
    if target==0x1018ad8:
     sample=next(it)&0x7fe;reads.append(sample);self.reg['r0']=sample
    elif target==0x1018a10:hooks.append('adc_init')
    elif target==self.gpio:hooks.append(['gpio',self.reg['r0'],self.reg['r1']])
    elif target==self.delay:hooks.append(['delay',self.reg['r0']])
    elif target==self.restart:hooks.append('restart_route');restarted=True;break
    else:raise AssertionError(f'Unapproved call {target:x}')
   elif m!='nop':raise AssertionError(f'Unsupported instruction: {trace[-1]}')
   self.reg['pc']=nextpc
  else:raise AssertionError('Instruction budget exceeded')
  return {'raw_reads':reads,'returned_value':None if restarted else self.reg['r0'],
          'failures':self.read(0x201f7,1),'adc_reinitialized':'adc_init' in hooks,
          'restart_route':restarted,'hooks':hooks,'instructions':len(trace),'trace':trace}

def battery_run(e,voltage=0,mode=0):
 regs={f'r{i}':0 for i in range(13)};regs.update(sp=0x2f000,lr=0xdead0001)
 pc={'1.09':0x1023f70,'1.10':0x1023ea4,'1.11':0x1023e9c}[e.version];cmp=(0,0);trace=[]
 calls=[i.operands[0].imm for i in e.cs.disasm(e.image[pc-0x1018000:pc-0x1018000+0x74],pc) if i.mnemonic=='bl']
 assert len(calls)==3 and calls[1]==calls[2]
 def value(op):return regs[e.cs.reg_name(op.reg)] if op.type==1 else op.imm
 def mem(op):
  m=op.mem;n=e.cs.reg_name(m.base)
  return (((pc+4)&~3) if n=='pc' else regs[n])+m.disp
 for _ in range(150):
  i=next(e.cs.disasm(e.image[pc-0x1018000:pc-0x1018000+4],pc,count=1));ops=i.operands;m=i.mnemonic
  trace.append(f'{pc:08x} {i.bytes.hex()} {m} {i.op_str}');nxt=pc+i.size
  dst=e.cs.reg_name(ops[0].reg) if ops and ops[0].type==1 else None
  if m=='push':
   regs['sp']-=4*len(ops)
   for n,o in enumerate(ops):e.write(regs['sp']+n*4,value(o),4)
  elif m=='pop':
   for n,o in enumerate(ops):regs[e.cs.reg_name(o.reg)]=e.read(regs['sp']+n*4,4)
   regs['sp']+=4*len(ops)
   break
  elif m in ['mov','movs']:regs[dst]=value(ops[1])
  elif m in ['ldr','ldrb']:regs[dst]=e.read(mem(ops[1]),4 if m=='ldr' else 1)
  elif m=='strb':e.write(mem(ops[1]),value(ops[0]),1)
  elif m=='cmp':cmp=(value(ops[0]),value(ops[1]))
  elif m in ['adds','subs']:regs[dst]=(value(ops[1])+(value(ops[2]) if m=='adds' else -value(ops[2])))&0xffffffff
  elif m=='uxtb':regs[dst]=value(ops[1])&255
  elif m=='bics':regs[dst]&=~value(ops[1])&0xffffffff
  elif m=='orrs':regs[dst]|=value(ops[1])
  elif m=='ands':regs[dst]&=value(ops[1])
  elif m in ['b','beq','bge','ble']:
   a,b=cmp
   if m=='b' or(m=='beq' and a==b)or(m=='bge' and a>=b)or(m=='ble' and a<=b):nxt=ops[0].imm
  elif m=='bl':
   t=ops[0].imm
   if t==calls[0]:regs['r0']=mode
   elif t==calls[1]:regs['r0']=voltage
   else:raise AssertionError(hex(t))
  elif m=='nop':pass
  else:raise AssertionError(trace[-1])
  pc=nxt
 else:raise AssertionError('budget')
 return {'voltage':voltage,'return':regs['r0'],'state_byte':e.read(0x20537,1),'trace':trace}

class Replay:
    def __init__(self,image,divider,mode,connected=True):
        self.image=image;self.mem={};self.write(0xf8560,divider,4);self.write(0x201aa,mode,1)
        self.write(0x20265,10,1);self.calls=[]
        self.write(0x20176,2 if connected else 0,1)
        self.cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);self.cs.detail=True
    def read(self,a,n):
        if BASE<=a and a+n<=BASE+len(self.image):return int.from_bytes(self.image[a-BASE:a-BASE+n],'little')
        return sum(self.mem.get(a+i,0)<<(i*8)for i in range(n))
    def write(self,a,v,n):
        assert not BASE<=a<BASE+104960
        for i in range(n):self.mem[a+i]=(v>>(8*i))&255
    def run(self,p,entry=ENTRY,args=None,hooks=None,targets=()):
        r={f'r{i}':0x12340000+i for i in range(13)};r.update(sp=0x2f000,lr=0xdead0001,pc=entry,r0=p)
        if args:r.update(args)
        hooks=hooks or {}
        original={k:r[k]for k in ('r4','r5','r6','r7','sp')};cmp=(0,0);trace=[]
        def val(op):return r[self.cs.reg_name(op.reg)]if op.type==ARM_OP_REG else op.imm&0xffffffff
        def addr(op,pc):
            assert op.type==ARM_OP_MEM
            name=self.cs.reg_name(op.mem.base)
            index=r[self.cs.reg_name(op.mem.index)] if op.mem.index else 0
            return (((pc+4)&~3)if name=='pc'else r[name])+op.mem.disp+index
        for step in range(500):
            pc=r['pc'];i=next(self.cs.disasm(self.image[pc-BASE:pc-BASE+4],pc,count=1),None)
            assert i,hex(pc)
            m=i.mnemonic;ops=i.operands;nxt=pc+i.size
            trace.append(f'{pc:08x} {i.bytes.hex()} {m} {i.op_str}')
            if m=='push':
                r['sp']-=4*len(ops)
                for j,o in enumerate(ops):self.write(r['sp']+4*j,val(o),4)
            elif m=='pop':
                for j,o in enumerate(ops):r[self.cs.reg_name(o.reg)]=self.read(r['sp']+4*j,4)
                r['sp']+=4*len(ops)
                if any(self.cs.reg_name(o.reg)=='pc'for o in ops):
                    nxt=r['pc']&~1
                    if nxt==0xdead0000:break
            elif m in ('mov','movs'):r[self.cs.reg_name(ops[0].reg)]=val(ops[1])
            elif m in ('ldr','ldrb','ldrh'):r[self.cs.reg_name(ops[0].reg)]=self.read(addr(ops[1],pc),{'ldr':4,'ldrb':1,'ldrh':2}[m])
            elif m in ('str','strb','strh'):self.write(addr(ops[1],pc),val(ops[0]),{'str':4,'strb':1,'strh':2}[m])
            elif m in ('add','adds','sub','subs'):
                dst=self.cs.reg_name(ops[0].reg);x=r[dst]if len(ops)==2 else val(ops[1]);y=val(ops[-1])
                r[dst]=((x-y)if m in ('sub','subs')else(x+y))&0xffffffff
            elif m in ('lsls','lsrs'):
                x=val(ops[1]);bits=val(ops[2]);r[self.cs.reg_name(ops[0].reg)]=((x<<bits)if m=='lsls'else(x>>bits))&0xffffffff
            elif m=='muls':r[self.cs.reg_name(ops[0].reg)]=(val(ops[1])*val(ops[2]))&0xffffffff
            elif m in ('uxtb','uxth'):r[self.cs.reg_name(ops[0].reg)]=val(ops[1])&(255 if m=='uxtb'else 65535)
            elif m=='mvns':r[self.cs.reg_name(ops[0].reg)]=~val(ops[1])&0xffffffff
            elif m=='ands':r[self.cs.reg_name(ops[0].reg)]&=val(ops[-1])
            elif m=='orrs':r[self.cs.reg_name(ops[0].reg)]|=val(ops[-1])
            elif m=='cmp':cmp=(val(ops[0]),val(ops[1]))
            elif m in ('b','beq','bne','bls','blo','bhs','bhi'):
                x,y=cmp
                if m=='b'or(m=='beq'and x==y)or(m=='bne'and x!=y)or(m=='bls'and x<=y)or(m=='blo'and x<y)or(m=='bhs'and x>=y)or(m=='bhi'and x>y):nxt=ops[0].imm
            elif m=='bl':
                target=ops[0].imm;r['lr']=nxt|1
                if target in hooks:hooks[target](self,r)
                elif target in (0x01018240,0x01018214):
                    assert r['r1'];assert r['r0']<0x80000000 and r['r1']<0x80000000
                    r['r0']//=r['r1']
                elif target in (STUB,0x01028138,0x01026378,0x0102c0f8) or target in targets:nxt=target
                elif target==0x0102a364:
                    self.calls.append(dict(name='activity_timeout_recompute',period=self.read(0x20265,1)));nxt=target
                else:raise AssertionError('Unknown call '+hex(target))
            elif m=='bx':
                nxt=val(ops[0])&~1
                if nxt==0xdead0000:break
            elif m!='nop':raise AssertionError('Unknown instruction '+trace[-1])
            r['pc']=nxt
        else:raise AssertionError('Instruction bound')
        assert all(r[k]==v for k,v in original.items()),'Callee-saved register or stack corruption'
        return dict(r0=r['r0'],stored_period=self.read(0x20265,1),load=self.read(0xe000e014,4),calls=self.calls,
                    activity_threshold=self.read(0x20188,4),trace=trace)
