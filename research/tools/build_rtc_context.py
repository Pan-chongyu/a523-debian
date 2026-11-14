"""Build a separate logger and cross-check its C encoding on the host."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
folder = root/'build/rtc-context'
folder.mkdir(exist_ok=True)
assert not (folder/'BUILD_COMPLETE.json').exists()
out = Path('/opt/a523-debian-20261109/tzx-rtc-context')
out.mkdir(exist_ok=True)
source = (root/'firmware/tzx_rtc_log.c').read_text()
source = source.replace('#include <asm/ptrace.h>', '#include <asm/ptrace.h>\n#include <asm/sysreg.h>\n#include "rtc_abort_pack.h"')
needle = 'static int on_die('
addition = '''static int record_abort(u64 pc, u32 esr)
{
    u32 words[3];
    unsigned long flags;
    if (!tzx_abort_pack(pc, read_sysreg(far_el1), esr, raw_smp_processor_id(), words))
        return 0;
    local_irq_save(flags);
    writel(0, gp);
    writel(words[1], gp + 4);
    writel(words[2], gp + 8);
    wmb();
    writel(words[0], gp);
    wmb();
    readl(gp);
    local_irq_restore(flags);
    return 1;
}

'''
assert source.count(needle) == 1
source = source.replace(needle, addition+needle)
needle = 'if (upper_32_bits(pc) == 0xffff8000 && upper_32_bits(lr) == 0xffff8000)'
assert source.count(needle) == 1
source = source.replace(needle, 'if (record_abort(pc, (u32)args->err))\n            ;\n        else '+needle)
(out/'tzx_rtc_log.c').write_text(source)
shutil.copy2(root/'firmware/rtc_abort_pack.h', out/'rtc_abort_pack.h')
(out/'Makefile').write_text('obj-m := tzx_rtc_log.o\n')
with (folder/'build.log').open('w') as log:
    subprocess.run(['make','-C','/opt/a523-debian-20261109/linux-7.3.3',
        'O=/opt/a523-debian-20261109/kernel-cpufreq-framework-build','M='+str(out),
        'ARCH=arm64','CROSS_COMPILE=aarch64-linux-gnu-','-j4','modules'],
        check=True,stdout=log,stderr=subprocess.STDOUT)
for name in ('tzx_rtc_log.c','rtc_abort_pack.h','tzx_rtc_log.ko'):
    shutil.copy2(out/name,folder/name)
sha = lambda data:hashlib.sha256(data).hexdigest()
digest = sha((folder/'tzx_rtc_log.ko').read_bytes())
runtime = (root/'firmware/tzx_rtc_log_runtime.py').read_text()
runtime = runtime.replace('80e8e0522faec7ead866a254667a3272ccd6939551ed2f13bce0f2aa1b3fca73',digest)
needle = "path = root / (('rtc-live-'"
assert runtime.count(needle) == 1
runtime = runtime.replace(needle, "from rtc_context_codec import decode_abort_record\ncontext = decode_abort_record((metadata,value_low,value_high))\nif context is not None:\n    report.update(context)\n"+needle)
compile(runtime,'runtime.py','exec')
(folder/'runtime.py').write_text(runtime)
shutil.copy2(root/'firmware/rtc_context_codec.py',folder/'rtc_context_codec.py')

# Run the exact C packing helper natively; decode its output independently.
harness = '''#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32; typedef uint64_t u64;
#include "rtc_abort_pack.h"
int main(void) {
    const u64 fars[] = {0xffff00013f680040ULL,0xffff8000806677f4ULL,
        0xfffffdff01234000ULL,0xffffffffff123000ULL,0x0000001234567000ULL,
        0xabcdef1234567890ULL};
    for (unsigned i=0;i<6;i++) for(unsigned cpu=0;cpu<8;cpu++) {
        u32 words[3];
        if(!tzx_abort_pack(0xffff8000806677f4ULL,fars[i],0x96001fc7U,cpu,words))return 2;
        printf("%llx %u %08x %08x %08x\\n",(unsigned long long)fars[i],cpu,words[0],words[1],words[2]);
    }
    u32 words[3];
    if(tzx_abort_pack(0xffff800078df9000ULL,0,0x96000007U,0,words))return 3;
    if(tzx_abort_pack(0xffff8000806677f5ULL,0,0x96000007U,0,words))return 4;
    if(tzx_abort_pack(0xffff8000806677f4ULL,0,0x86000007U,0,words))return 5;
    return 0;
}
'''
(out/'codec_test.c').write_text(harness)
subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-o',str(out/'codec-test'),str(out/'codec_test.c')],check=True)
output = subprocess.check_output([str(out/'codec-test')],text=True)
(folder/'codec-vectors.txt').write_text(output)
sys.path.insert(0,str(folder))
from rtc_context_codec import decode_abort_record
vectors = 0
for row in output.splitlines():
    far,cpu,*words = row.split()
    result = decode_abort_record(tuple(int(word,16) for word in words))
    assert result['fault_pc']=='0xffff8000806677f4' and result['cpu']==int(cpu)
    assert int(result['fault_esr_preserved_bits'],16)==0x96001fc7
    if int(far,16)>>40==0xabcdef:
        assert not result['fault_far_complete'] and result['fault_far'] is None
    else:assert int(result['fault_far'],16)==int(far,16)
    vectors += 1
assert vectors==48 and decode_abort_record((0x54580705,0x806677f4,0x80144e24)) is None
record = {'state':'built_and_codec_checked_not_installed','C_to_Python_vectors':vectors,
    'RTC_words':'existing GP1..3 only','kernel_changed':False,
    'ESR_preserved_mask':'0xfe001fff','files':{p.name:sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}}
(folder/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('RTC_CONTEXT_BUILT',json.dumps(record),flush=True)
