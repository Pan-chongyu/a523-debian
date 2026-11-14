// SPDX-License-Identifier: MIT
/* Request a bounded, thermally capped boost, then exec as the invoking user. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    struct timeval limit = {.tv_sec = 0, .tv_usec = 120000};
    char reply[8];
    int fd;
    if (argc < 2) {
        fputs("Usage: tzx-launch PROGRAM [ARGUMENTS...]\n", stderr);
        return 2;
    }
    fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd >= 0) {
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof(limit));
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &limit, sizeof(limit));
        strcpy(address.sun_path, "/run/tzx-app-boost.sock");
        if (!connect(fd, (struct sockaddr *)&address, sizeof(address))) {
            if (send(fd, "boost\n", 6, MSG_NOSIGNAL) == 6)
                (void)recv(fd, reply, sizeof(reply), 0);
        }
        close(fd);
    }
    /* No setuid bit, subprocess, shell expansion, or privileged execution. */
    execvp(argv[1], argv + 1);
    perror(argv[1]);
    return errno == ENOENT ? 127 : 126;
}
