"""Execute the actual patched descriptor builder against merged/high-PA SG cases."""
import json
from pathlib import Path
import re
import subprocess
import sys

folder = Path(sys.argv[1])
text = (folder/'sunxi-mmc-after.c').read_text()
start = text.index('static void sunxi_mmc_init_idma_des(')
end = text.index('\nstatic int sunxi_mmc_map_dma(', start)
function = text[start:end]
assert 'struct mmc_data *data, int nents)' in function
macros = '\n'.join(re.findall(r'^#define SDXC_IDMAC_DES0_.*$', text, re.M))
header = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define BIT(n) (UINT32_C(1)<<(n))
#define min(a,b) ((a)<(b)?(a):(b))
#define cpu_to_le32(x) ((uint32_t)(x))
#define wmb() ((void)0)
typedef uint64_t dma_addr_t;
struct sunxi_idma_des { uint32_t config,buf_size,buf_addr_ptr1,buf_addr_ptr2; };
struct scatterlist { dma_addr_t address; unsigned int dma_length,length,offset; };
struct mmc_data { struct scatterlist *sg; unsigned int sg_len; };
struct config { unsigned int idma_des_size_bits,idma_des_shift; };
struct sunxi_mmc_host { void *sg_cpu; dma_addr_t sg_dma; struct config *cfg; };
#define for_each_sg(list,sg,count,i) for((i)=0,(sg)=(list);(i)<(unsigned int)(count);(i)++,(sg)++)
#define sg_dma_address(sg) ((sg)->address)
#define sg_dma_len(sg) ((sg)->dma_length)
'''
tests = r'''
static void check(struct sunxi_idma_des *d, unsigned int count,
                  const uint64_t *address,const unsigned int *length,
                  uint64_t base,unsigned int shift)
{
    for(unsigned int i=0;i<count;i++) {
        uint32_t flags=SDXC_IDMAC_DES0_CH|SDXC_IDMAC_DES0_OWN;
        if(i==0) flags|=SDXC_IDMAC_DES0_FD;
        if(i+1==count) flags|=SDXC_IDMAC_DES0_LD|SDXC_IDMAC_DES0_ER;
        else flags|=SDXC_IDMAC_DES0_DIC;
        assert(d[i].config==flags);
        assert(d[i].buf_size==length[i]);
        assert(d[i].buf_addr_ptr1==(uint32_t)(address[i]>>shift));
        assert(d[i].buf_addr_ptr2==(i+1==count?0:(uint32_t)((base+(i+1)*16)>>shift)));
    }
    const unsigned char *unused=(const unsigned char *)(d+count);
    for(unsigned int i=0;i<(257-count)*16;i++) assert(unused[i]==0xcc);
}
int main(void)
{
    struct sunxi_idma_des descriptors[257];
    struct scatterlist sg[256];
    struct config cfg={12,2};
    struct sunxi_mmc_host host={descriptors,UINT64_C(0x100010000),&cfg};
    struct mmc_data data={sg,3};
    uint64_t addresses[256]; unsigned int lengths[256];
    memset(descriptors,0xcc,sizeof(descriptors));memset(sg,0xcc,sizeof(sg));
    sg[0]=(struct scatterlist){UINT64_C(0x100200000),12288,4096,0};
    sunxi_mmc_init_idma_des(&host,&data,1);
    addresses[0]=UINT64_C(0x100200000);addresses[1]=UINT64_C(0x100201000);addresses[2]=UINT64_C(0x100202000);
    lengths[0]=lengths[1]=lengths[2]=0;
    check(descriptors,3,addresses,lengths,host.sg_dma,2);
    puts("MERGED_THREE_SEGMENTS_SPLIT_AND_HIGH_PA_PASS");
    memset(descriptors,0xcc,sizeof(descriptors));memset(sg,0xcc,sizeof(sg));
    sg[0]=(struct scatterlist){UINT64_C(0x100300000),6144,4096,0};
    sg[1]=(struct scatterlist){UINT64_C(0x13fff0000),512,512,0};
    data.sg_len=4;sunxi_mmc_init_idma_des(&host,&data,2);
    addresses[0]=UINT64_C(0x100300000);addresses[1]=UINT64_C(0x100301000);addresses[2]=UINT64_C(0x13fff0000);
    lengths[0]=0;lengths[1]=2048;lengths[2]=512;
    check(descriptors,3,addresses,lengths,host.sg_dma,2);
    puts("MAPPED_COUNT_IGNORES_POISON_ORIGINAL_TAIL_PASS");
    memset(descriptors,0xcc,sizeof(descriptors));
    for(unsigned int i=0;i<256;i++) {
        sg[i]=(struct scatterlist){UINT64_C(0x100400000)+i*4096,4096,4096,0};
        addresses[i]=sg[i].address;lengths[i]=0;
    }
    data.sg_len=256;sunxi_mmc_init_idma_des(&host,&data,256);
    check(descriptors,256,addresses,lengths,host.sg_dma,2);
    puts("MAXIMUM_TABLE_256_DESCRIPTORS_GUARD_PASS");
    cfg.idma_des_shift=0;host.sg_dma=UINT64_C(0x41000000);
    memset(descriptors,0xcc,sizeof(descriptors));
    sg[0]=(struct scatterlist){UINT64_C(0x42000000),512,512,0};
    data.sg_len=1;sunxi_mmc_init_idma_des(&host,&data,1);
    addresses[0]=sg[0].address;lengths[0]=512;
    check(descriptors,1,addresses,lengths,host.sg_dma,0);
    puts("UNSHIFTED_SINGLE_DESCRIPTOR_PASS");
    return 0;
}
'''
source = folder/'descriptor-cases.c'
source.write_text(header+macros+'\n'+function+tests)
subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                '-o', str(folder/'descriptor-cases'), str(source)], check=True)
result = subprocess.run([str(folder/'descriptor-cases')], capture_output=True, text=True, check=True)
record = {'actual_driver_function_executed': True, 'sanitizers': 'address,undefined',
          'cases': result.stdout.splitlines(), 'result': 'PASS'}
(folder/'DESCRIPTOR_CASES.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record), flush=True)
