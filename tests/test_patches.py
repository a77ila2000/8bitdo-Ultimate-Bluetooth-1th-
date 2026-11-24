from pathlib import Path
import io
import zipfile
import os
import pytest
import patcher
import patch_source as source
import receiver_format
from vendor import cryptdo8
from tests.instruction_vm import ThumbSampler, battery_run, Replay


def test_updater_preserves_required_data_subdirectory(tmp_path, monkeypatch):
    files={'8BitDo Firmware Updater.exe':b'exe', '8BitDoFirmwareUpdaterTools.dll':b'dll',
           'data/versions.txt':b'2.52', 'data/debugLog.txt':b'', 'data/Autoupdate.exe':b'auto'}
    blob=io.BytesIO()
    with zipfile.ZipFile(blob,'w') as z:
        for name,data in files.items():z.writestr('8BitDo_Firmware_Updater_Win/'+name,data)
    monkeypatch.setattr(patcher,'check_stock',lambda data,kind:None)
    monkeypatch.setattr(patcher,'DLL_SHA',patcher.sha(b'dll'))
    monkeypatch.setattr(patcher,'UPDATER_SHA',patcher.sha(b'exe'))
    patcher.prepare_updater(blob.getvalue(),tmp_path)
    for name,data in files.items():assert (tmp_path/name).read_bytes()==data
    assert not (tmp_path/'Autoupdate.exe').exists()
    (tmp_path/'data/debugLog.txt').write_bytes(b'local runtime log')
    patcher.prepare_updater(blob.getvalue(),tmp_path)
    assert (tmp_path/'data/debugLog.txt').read_bytes()==b'local runtime log'


@pytest.fixture(scope='module')
def raw():
    folder = Path(os.environ.get('ULTIMATE_STOCK_DIR', Path(__file__).resolve().parents[1] / 'cache'))
    if not (folder / 'controller-v1.11.dat').exists():
        pytest.fail('Run python patcher.py prepare --skip-updater before testing')
    return {kind: (folder / name).read_bytes() for kind, name in
            [('controller', 'controller-v1.11.dat'), ('receiver', 'receiver-v1.04.dat')]}


@pytest.fixture(scope='module')
def images(raw):
    result = {**patcher.controller_images(raw['controller']), **patcher.receiver_images(raw['receiver'])}
    def decode(data):
        return cryptdo8.decrypt_section(data, cryptdo8.parse_image(data)[0], cryptdo8.CIPHERS['yichip'])
    return decode(raw['controller']), decode(result['controller-conservative.dat']), decode(result['controller-enhanced.dat']), result


def test_exact_recorded_outputs_and_no_diagnostic_tail(images):
    original, conservative, final, outputs = images
    assert len(original) == len(conservative) == 104960
    assert len(final) == 105472
    assert patcher.sha(final) == '825e03d4c9f920e885bdb6a20fee519a4a28863d51ba4eb91e66f3b8e53a997b'
    for name, digest in patcher.EXPECTED.items():
        assert patcher.sha(outputs[name + '.dat']) == digest
    source.verify_payloads(final)


def test_reject_wrong_original_and_already_modified_input(raw, images):
    for kind, build in [('controller', patcher.controller_images), ('receiver', patcher.receiver_images)]:
        data = bytearray(raw[kind]); data[-1] ^= 1
        for wrong in (bytes(data), raw[kind][:-1], raw[kind] + b'\0', raw['receiver' if kind == 'controller' else 'controller']):
            with pytest.raises(ValueError): build(wrong)
    with pytest.raises(ValueError): patcher.controller_images(images[3]['controller-enhanced.dat'])


def test_reject_wrong_preimage_overlap_and_bounds():
    for edits, size in [
        ([dict(offset='0x0', before='01', after='02')], 4),
        ([dict(offset='0x0', before='0000', after='0202'), dict(offset='0x1', before='00', after='01')], 4),
        ([dict(offset='0x4', before='00', after='01')], 4),
        ([], 3), ([], 517),
    ]:
        with pytest.raises(ValueError): patcher.apply_edits(bytes(4), edits, size)


def test_receiver_incomplete_crc_edit_rejected(raw):
    parsed = receiver_format.verify(raw['receiver'])
    decoded = bytearray(parsed['decoded'])
    decoded[parsed['app']['position'] + 0x10ee4] = 2
    broken = raw['receiver'][:28+0x4000] + receiver_format.sfc(decoded, parsed['key'])
    with pytest.raises(AssertionError): receiver_format.verify(broken)


def test_adc_original_bug_and_exhaustive_corrected_boundary(images):
    original, corrected = images[:2]
    before = ThumbSampler('1.11', original).run([0,0,0,0,1500])
    assert before['failures'] == 1 and before['adc_reinitialized']
    assert not before['restart_route']  # Fifth-valid alone cannot accumulate six failures.
    count = 0
    for channel in range(6):
        low, high = (0x800,0xf80) if channel < 4 else (0x880,0xfe0)
        for state in range(256):
            for position in range(1,6):
                vm = ThumbSampler('1.11', corrected); vm.write(0x201f7,state,1)
                result = vm.run([0]*(position-1)+[1500]+[0]*(5-position),channel,low,high)
                assert result['returned_value'] == 3000 and result['failures'] == 0
                assert not result['adc_reinitialized'] and not result['restart_route']
                count += 1
            observations = []
            for image in (original, corrected):
                vm = ThumbSampler('1.11', image);vm.write(0x201f7,state,1)
                observations.append(vm.run([0]*5,channel,low,high))
            for key in ('returned_value','failures','adc_reinitialized','restart_route','hooks'):
                assert observations[0][key] == observations[1][key]
            count += 1
        for value in (low,low+4,high-4,high):
            result = ThumbSampler('1.11', corrected).run([value//2]*5,channel,low,high)
            assert result['adc_reinitialized'] == (value in (low,high))
            count += 1
    assert count == 9240


def test_battery_original_failure_and_all_corrected_states(images):
    original, corrected = images[:2]
    vm = ThumbSampler('1.11',original)
    assert [battery_run(vm,0,1)['state_byte'] for _ in range(5)] == [1,3,7,15,143]
    count = 0
    for mode,threshold in ((0,2200),(1,3400)):
        for voltage in (threshold-1,threshold,threshold+1):
            for state in range(256):
                low,high=state&127,state&128
                if voltage<threshold:
                    low+=1
                    if low>10:low=10;high=128
                elif low>0:low-=1
                vm=ThumbSampler('1.11',corrected);vm.write(0x20537,state,1)
                result=battery_run(vm,voltage,mode)
                assert result['state_byte']==high|low
                assert result['return']==bool((high|low)&128)
                count+=1
    assert count==1536
    for sequence,expected in [([0]*11,list(range(1,11))+[138]),([0,10000]*15,[1,0]*15),
                              ([0]*5+[10000]*5,[1,2,3,4,5,4,3,2,1,0])]:
        vm=ThumbSampler('1.11',corrected)
        assert [battery_run(vm,v,1)['state_byte'] for v in sequence]==expected
    vm=ThumbSampler('1.11',corrected)
    states=[battery_run(vm,v,1)['state_byte'] for v in [0]*11+[10000]*15]
    assert all(s&128 for s in states[10:])


def test_final_schedule_actual_thumb_1080_cases(images):
    final=images[2];count=0
    for mode in (0,1,2,255):
        for rf in (0,1,255):
            for period in (2,5,10):
                for elapsed in range(5):
                    for tick in (0,1,100,65535,1000000,0xfffffff0):
                        vm=Replay(final,0,mode)
                        vm.write(0x20595,rf,1);vm.write(0x20265,period,1);vm.write(source.TICK,tick,4)
                        events=[]
                        def noop(memory,regs):pass
                        def work(memory,regs):memory.write(source.TICK,tick+elapsed,4);regs['r0']=0
                        def zero(memory,regs):regs['r0']=0
                        def original(memory,regs):
                            events.append('original')
                            memory.write(regs['r0']+4,memory.read(source.TICK,4)+1+regs['r1']//period,4)
                        hooks={0x010285f8:noop,0x0101bc00:noop,0x0101fe34:work,0x010238a4:zero,
                               0x010217fc:noop,0x01023c68:zero,0x0102bcf0:original,0x0102b9a8:noop}
                        vm.run(source.TIMER,entry=0x0101dae4,hooks=hooks,targets=(0x0101daec,0x01023700,source.START,source.ARM))
                        fast=mode==1 and period==2
                        assert vm.read(source.TIMER+4,4)==tick+1+(0 if fast else elapsed)
                        assert bool(events)==(not fast)
                        count+=1
    assert count==1080


def test_timing_reload_and_activity_actual_thumb(images):
    image=images[2]
    for divider in (0,1,3,15):
        clock=192000000//(divider+2)
        for mode in (0,1):
            for request in (2,5,10,15,20):
                vm=Replay(image,divider,mode)
                result=vm.run(request)
                fast=request==2 or (mode==1 and request in (5,10))
                expected=clock//500 if fast else (clock//200)*((request//5)&255)
                assert result['load']==expected-1
                assert result['stored_period']==(2 if fast else request)
    for flags in ((0,0),(1,0),(0,1),(1,1)):
        for word in (0xffffffff,0x7f7f7f7f,0x80808080,0x7f7f7f76,0x7f7f7f77,0x7f7f7f87,0x7f7f7f88):
            vm=Replay(image,0,1);vm.write(0x21604,flags[0],1);vm.write(0x22084,flags[1],1);vm.write(0x20238,word,4)
            result=vm.run(0,entry=source.ACTIVITY,targets=(0x01023f1c,))
            active=bool(any(flags) or (word!=0xffffffff and any(not 119<=((word>>s)&255)<=135 for s in range(0,32,8))))
            assert result['r0']==int(active)
