"""Exercise the real loader on the actual bundle with injected I/O/CRC faults."""
import json,re,subprocess
from fel_device import ROOT
task='/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian'
source=(ROOT/'firmware/chain_retry_loader.c').read_text()
# Only the two ARM barrier statements are replaced for the host build.
source=source.replace('__asm__ volatile("dsb sy":::"memory");','')
source=source.replace('__asm__ volatile("dsb sy; isb":::"memory");','')
assert '__asm__' not in source
harness=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static unsigned char *disk;
static size_t disk_size;
static unsigned mode,slower,jumped,reads;
static void mapping(unsigned addr,size_t size) {
    size=(size+4095)&~4095U;
    void *p=mmap((void *)(uintptr_t)addr,size,PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
    if(p==MAP_FAILED){perror("mmap");exit(3);}
}
int cold_emmc_init(void){return 0;}
int cold_emmc_slower(void){slower++;return 0;}
int cold_emmc_read(unsigned lba,void *out){
    size_t offset=(lba-4096ULL)*512;reads++;
    if(offset+512>disk_size)return -1;
    if(mode==3&&lba==4100)return -1;
    memcpy(out,disk+offset,512);
    if(lba==4100&&(mode==2||(mode==1&&!slower)))((unsigned char *)out)[7]^=0x80;
    return 0;
}
void enter_arm64(unsigned address){if(address!=0x54000)exit(4);jumped++;}
int main(int argc,char **argv){
    if(argc!=3)return 2;mode=strtoul(argv[2],0,0);
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    fseek(f,0,SEEK_END);disk_size=ftell(f);rewind(f);
    disk=malloc(disk_size);if(fread(disk,1,disk_size,f)!=disk_size)return 2;fclose(f);
    mapping(0x30000,4096);mapping(0x07090000,4096);
    mapping(0x02000000,8192);mapping(0x02050000,4096);
    mapping(0x48080000,0x1f80000);mapping(0x47000000,0x100000);
    mapping(0x60000000,0x1000000);mapping(0x4a000000,0x100000);mapping(0x54000,0xc000);
    if(mode==4)disk[16]^=1;
    if(mode==5){
        ((uint32_t *)disk)[10]=0x47000000;((uint32_t *)disk)[4]=0;
        ((uint32_t *)disk)[4]=~crc32_update(~0U,disk,512);
    }
    chain_load();
    unsigned stage=REG(0x07090110);
    int ok=mode==0?(jumped==1&&!slower):
        mode==1?(jumped==1&&slower==1):
        mode==2?(!jumped&&slower==2&&stage==0xa52347c0):
        mode==3?(!jumped&&stage==0xa52347f0):
        mode==4?(!jumped&&stage==0xa52347e3):
        mode==5?(!jumped&&stage==0xa52347e4):0;
    printf("mode=%u result=%s jumps=%u slower=%u reads=%u stage=%08x\n",mode,ok?"PASS":"FAIL",jumped,slower,reads,stage);
    return ok?0:1;
}
'''
(ROOT/'build/check-retry-loader-host.c').write_text(source+harness,encoding='ascii',newline='\n')
subprocess.run(['wsl','-d','Ubuntu-22.04','--','cc','-O1','-fno-pie','-no-pie',
                '-fsanitize=undefined','-Wno-int-to-pointer-cast',
                task+'/build/check-retry-loader-host.c','-o','/tmp/tzx-retry-loader-check'],check=True)
results=[]
for mode in range(6):
    run=subprocess.run(['wsl','-d','Ubuntu-22.04','--','/tmp/tzx-retry-loader-check',
        task+'/build/recovery-new-image-old-dtb-slot/linux-bundle.bin',str(mode)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    assert b'runtime error:' not in run.stderr.lower(),run.stderr
    results.append(run.stdout.decode().strip())
report={'result':'PASS','tests':results,'hardware_tested':False,
        'scope':'Actual chain_retry_loader.c, real five-item bundle; ARM barriers omitted only for host build'}
text=json.dumps(report,indent=2)
(ROOT/'evidence/retry-loader-host-verification.json').write_text(text,encoding='utf8')
print(text)
