// SPDX-License-Identifier: GPL-2.0-only
/* Freeze the root filesystem across an experimental card-protocol change.
 * A static, locked-in-RAM helper and independent watchdog keep recovery
 * available even when the new card mode cannot complete a request. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <linux/watchdog.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC,&t);
    return t.tv_sec+t.tv_nsec/1e9;
}

int main(int argc,char **argv)
{
    char ios[2048]={0};
    int root,profile,status,sysrq,wd,done[2],seconds=16,error=0,result;
    pid_t child;
    ssize_t n;
    if(geteuid() || argc!=2 ||
       (strcmp(argv[1],"200,100") && strcmp(argv[1],"400,100")))return 64;
    setbuf(stdout,NULL);
    root=open("/",O_RDONLY|O_DIRECTORY);
    profile=open("/sys/module/tzx_emmc_hs_lease/parameters/profile",O_WRONLY);
    status=open("/sys/kernel/debug/mmc0/ios",O_RDONLY);
    sysrq=open("/proc/sysrq-trigger",O_WRONLY);
    wd=open("/dev/watchdog",O_WRONLY|O_CLOEXEC);
    if(root<0 || profile<0 || status<0 || sysrq<0 || wd<0 || pipe(done) ||
       ioctl(wd,WDIOC_SETTIMEOUT,&seconds) || mlockall(MCL_CURRENT|MCL_FUTURE)) {
        perror("transition guard setup");return 1;
    }
    child=fork();
    if(child<0){perror("fork");return 1;}
    if(!child) {
        struct pollfd p={.fd=done[0],.events=POLLIN};
        double end=now()+120;
        close(done[1]);
        mlockall(MCL_CURRENT|MCL_FUTURE);
        while(now()<end) {
            if(poll(&p,1,1000)>0 && (p.revents&POLLIN)) {
                write(wd,"V",1);close(wd);_exit(0);
            }
            if(write(wd,".",1)!=1)break;
        }
        write(sysrq,"b",1);
        for(;;)pause();
    }
    close(done[0]);close(wd);
    syncfs(root);
    printf("ROOT_FREEZE_BEGIN %s\n",argv[1]);
    if(ioctl(root,FIFREEZE,0)){perror("FIFREEZE");error=1;goto finish;}
    n=write(profile,argv[1],strlen(argv[1]));
    result=errno;
    if(read(status,ios,sizeof(ios)-1)<0)ios[0]=0;
    printf("CARD_TRANSITION_RETURN bytes=%zd errno=%d ios=%s\n",n,n<0?result:0,ios);
    if(n!=(ssize_t)strlen(argv[1])) {
        error=2;
        if(!strstr(ios,"mmc DDR52") || !strstr(ios,"25000000 Hz")) {
            printf("FROZEN_ROOT_PROTOCOL_FAILURE_REBOOT\n");
            write(sysrq,"b",1);
            for(;;)pause();
        }
    }
    if(ioctl(root,FITHAW,0)){perror("FITHAW");write(sysrq,"b",1);for(;;)pause();}
    printf("ROOT_THAW_COMPLETE\n");
finish:
    write(done[1],"x",1);close(done[1]);waitpid(child,NULL,0);
    close(sysrq);close(status);close(profile);close(root);
    return error;
}
