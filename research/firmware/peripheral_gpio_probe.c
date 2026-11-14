/* SPDX-License-Identifier: MIT
 * Short, reversible tests of two tablet reference-board signals. Pins are
 * selected by name through the GPIO ABI, never by an assumed chip offset.
 * They are candidates until an actual peripheral responds on this board.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int find_pin(const char *name, unsigned int *offset) {
    char path[64];
    for (unsigned int c=0;c<16;c++) {
        snprintf(path,sizeof(path),"/dev/gpiochip%u",c);
        int fd=open(path,O_RDONLY|O_CLOEXEC);
        if(fd<0)continue;
        struct gpiochip_info ci={0};
        if(ioctl(fd,GPIO_GET_CHIPINFO_IOCTL,&ci)<0){close(fd);continue;}
        /* This kernel does not publish pin names as gpio-line-names.
         * Its main PIO uses A-based offsets; R_PIO starts at PL0. */
        unsigned int fallback=~0U;
        if(!strcmp(name,"PH10")&&!strcmp(ci.label,"2000000.pinctrl"))fallback=234;
        if(!strcmp(name,"PM1")&&!strcmp(ci.label,"7022000.pinctrl"))fallback=33;
        if(!strcmp(name,"PM5")&&!strcmp(ci.label,"7022000.pinctrl"))fallback=37;
        if(!strcmp(name,"PL7")&&!strcmp(ci.label,"7022000.pinctrl"))fallback=7;
        for(unsigned int n=0;n<ci.lines;n++) {
            struct gpio_v2_line_info li={.offset=n};
            if(ioctl(fd,GPIO_V2_GET_LINEINFO_IOCTL,&li)<0)continue;
            if(strcmp(li.name,name) && !(li.name[0]==0 && n==fallback))continue;
            printf("%s: %s offset %u consumer=%s flags=%llx\n",name,path,n,
                   li.consumer,(unsigned long long)li.flags);
            if(li.flags & GPIO_V2_LINE_FLAG_USED){close(fd);errno=EBUSY;return -1;}
            *offset=n;return fd;
        }
        close(fd);
    }
    errno=ENOENT;return -1;
}
static int value(int fd,unsigned int mask,int v){
    struct gpio_v2_line_values lv={.mask=mask,.bits=v?mask:0};
    return ioctl(fd,GPIO_V2_LINE_SET_VALUES_IOCTL,&lv);
}
int main(int argc,char **argv){
    char cid[64];FILE *f=fopen("/sys/class/block/mmcblk0/device/cid","r");
    if(!f||!fgets(cid,sizeof(cid),f))return 10;
    fclose(f);
    if(strcmp(cid,"3e01ff55454d20202010209170281b59\n"))return 11;
    int interactive=argc==3&&!strcmp(argv[1],"touch")&&!strcmp(argv[2],"--interactive");
    if((argc!=2&&!interactive) || (strcmp(argv[1],"radio")&&strcmp(argv[1],"radio-common")&&strcmp(argv[1],"touch"))) {
        fprintf(stderr,"Usage: %s radio|radio-common|touch (20 seconds)\n",argv[0]);
        return 2;
    }
    int common=!strcmp(argv[1],"radio-common");
    const char *pin=strcmp(argv[1],"touch")?"PM1":"PH10";
    unsigned int offset=0;int chip=find_pin(pin,&offset);
    if(chip<0){perror("find unused candidate GPIO");return 12;}
    struct gpio_v2_line_request req={0};
    req.offsets[0]=offset;req.num_lines=1;
    if(common){
        const char *extra[]={"PM5","PL7"};
        for(unsigned n=0;n<2;n++){
            int fd=find_pin(extra[n],&offset);
            if(fd<0){perror("find common radio signal");close(chip);return 17;}
            close(fd);req.offsets[req.num_lines++]=offset;
        }
    }
    unsigned int mask=(1U<<req.num_lines)-1;
    snprintf(req.consumer,sizeof(req.consumer),"tzx-peripheral-probe");
    req.config.flags=GPIO_V2_LINE_FLAG_OUTPUT;
    if(ioctl(chip,GPIO_V2_GET_LINE_IOCTL,&req)<0){perror("request");close(chip);return 13;}
    /* The reference signals are active high. Release to low after the test. */
    if(value(req.fd,mask,0)<0){perror("low");return 14;}
    usleep(20000);
    if(value(req.fd,mask,1)<0){perror("high");return 15;}
    printf("%s candidate %s HIGH for 20 seconds\n",argv[1],pin);fflush(stdout);
    if(interactive){
        struct pollfd input={.fd=STDIN_FILENO,.events=POLLIN};
        while(poll(&input,1,60000)>0){
            char command;
            if(read(STDIN_FILENO,&command,1)!=1||command=='q')break;
            if(command=='r'){
                if(value(req.fd,mask,0)<0)break;
                usleep(20000);
                if(value(req.fd,mask,1)<0)break;
                usleep(30000);
            }
        }
    }else sleep(20);
    int ret=value(req.fd,mask,0);close(req.fd);close(chip);
    puts("Candidate signal LOW; GPIO released");
    return ret<0?16:0;
}
