/* SPDX-License-Identifier: MIT
 * Start the previously disabled CPU4-7 PLL at 480 MHz, the same frequency
 * already used by CPU0-3. Register sequence checked against SyterKit sun55iw3.
 * No PMIC, DDR or DSU settings are changed.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
int main(void){
    char cid[64];FILE *f=fopen("/sys/class/block/mmcblk0/device/cid","r");
    if(!f||!fgets(cid,sizeof(cid),f))return 14;
    fclose(f);
    if(strncmp(cid,"3e01ff55454d2020",16))return 15;
    int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)return 10;
    volatile uint32_t *r=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x08817000);
    if(r==MAP_FAILED)return 11;
    uint32_t original=r[3],mux=r[0x64/4];
    printf("CPUB PLL=%08x MUX=%08x\n",original,mux);
    if((mux&(3U<<24))==3U<<24){puts("CPUB already uses its PLL");return 0;}
    if((mux&(3U<<24))!=0 || original!=0x48801400){puts("Unrecognized reset state; refused");return 12;}
    r[3]=0xe4801400;__sync_synchronize();
    unsigned n;
    for(n=0;n<1000;n++){if(r[3]&(1U<<28))break;usleep(100);}
    if(n==1000){r[3]=original;puts("PLL lock failed; restored");return 13;}
    usleep(20);r[3]=(r[3]|(1U<<27)|(1U<<26))&~(1U<<29);__sync_synchronize();usleep(20);
    r[0x64/4]=(mux&~((3U<<24)|(1U<<16)))|(3U<<24);
    __sync_synchronize();
    printf("CPUB PLL=%08x MUX=%08x; 480 MHz selected\n",r[3],r[0x64/4]);
    munmap((void*)r,4096);close(fd);return 0;
}
