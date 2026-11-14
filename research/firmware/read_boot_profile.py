"""Read the reserved counters without writing MMIO."""
import json
import mmap
import os
from pathlib import Path
import struct

fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    def read(addr,n):
        base=addr&~4095
        with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=base) as m:
            # /dev/mem is Device memory: forbid memcpy's vector/unaligned reads.
            return b''.join(struct.pack('<I',struct.unpack_from('<I',m,addr-base+i)[0])
                for i in range(0,n,4))
    fields=struct.unpack('<II5Q7Ii',read(0x2dc00,80))
    names=('magic','version','start','init_end','read_ticks','crc_ticks','last','reads','crcs',
           'cpua_pll','cpua_mux','mmc_clock','mmc_width','counter_hz','last_read_error')
    profile=dict(zip(names,fields))
    assert profile['magic']==0xa523f101 and profile['version']==1
    print('RAW_BOOT_PROFILE',json.dumps(profile),flush=True)
    # ROM has not necessarily programmed CNTFRQ; preserve it as evidence.
    # The same physical counter is sourced by the board's 24 MHz oscillator.
    hz=24000000
    profile['seconds_counter_basis_hz']=hz
    profile['seconds']=dict(init=(profile['init_end']-profile['start'])/hz,
        reads=profile['read_ticks']/hz,CRC=profile['crc_ticks']/hz,
        total=(profile['last']-profile['start'])/hz,
        other=(profile['last']-profile['init_end']-profile['read_ticks']-profile['crc_ticks'])/hz)
    profile['early_CPUB']=[hex(v) for v in struct.unpack('<6I',read(0x2df40,24))]
    profile['boot_width_receipt']=[hex(v) for v in struct.unpack('<8I',read(0x2df80,32))]
    profile['CRC_or_cache_receipt']=[hex(v) for v in struct.unpack('<6I',read(0x2dfc0,24))]
finally:os.close(fd)
profile['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print('BOOT_PROFILE_COUNTERS',json.dumps(profile,indent=2),flush=True)
