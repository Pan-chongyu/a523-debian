"""Compile the loader's actual C checksum routines and compare with zlib."""
from pathlib import Path
import random
import struct
import subprocess
import zlib
from fel_device import ROOT

text=(ROOT/'firmware/chain_loader.c').read_text()
source=text[text.index('static uint32_t crc_table'):text.index('void chain_load(void)')]
source='#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n'+source+'''
int main(void) {
    uint32_t length;
    crc32_init();
    while (fread(&length,4,1,stdin)==1) {
        unsigned char *p=malloc(length+1);
        if (!p || fread(p,1,length,stdin)!=length) return 2;
        printf("%08x\\n",~crc32_update(0xffffffff,p,length));
        free(p);
    }
    return ferror(stdin)?3:0;
}
'''
task_path='/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian'
(ROOT/'build/check-loader-crc.c').write_text(source,encoding='ascii',newline='\n')
subprocess.run(['wsl','-d','Ubuntu-22.04','--','cc','-O2','-Wall','-Wextra',
                task_path+'/build/check-loader-crc.c','-o','/tmp/tzx-check-loader-crc'],check=True)
rng=random.Random(523)
cases=[b'',b'123456789']+[rng.randbytes(n) for n in (1,3,4,31,32,127,128,511,512,513,4096,65535,65536,131072)]
packet=b''.join(struct.pack('<I',len(data))+data for data in cases)
run=subprocess.run(['wsl','-d','Ubuntu-22.04','--','/tmp/tzx-check-loader-crc'],input=packet,
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
observed=[int(x,16) for x in run.stdout.splitlines()]
expected=[zlib.crc32(data) for data in cases]
assert observed==expected,(observed,expected)
report=f'PASS: actual loader C CRC equals Python zlib for {len(cases)} independent vectors, including canonical 123456789 and 512-byte sector boundaries.\n'
(ROOT/'evidence/loader-crc-verification.txt').write_text(report,encoding='utf8')
print(report,end='')
