/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Bounded 8x16 text renderer for the reserved, right-landscape boot buffer. */
#define _DEFAULT_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

static int exact(void *data, size_t size)
{
    unsigned char *p = data;
    while (size) {
        ssize_t n = read(STDIN_FILENO, p, size);
        if (n <= 0) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
int main(int argc, char **argv)
{
    unsigned char font[4096];
    char text[8193];
    uint32_t n, *canvas = malloc(4096000);
    volatile uint32_t *fb;
    int fd;
    FILE *f;
    if (argc != 2 || !canvas || !(f = fopen(argv[1], "rb"))) return 1;
    if (fread(font, 1, sizeof(font), f) != sizeof(font)) return 2;
    fclose(f);
    fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) return 3;
    fb = mmap(NULL, 4096000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x42400000);
    if (fb == MAP_FAILED) return 4;
    while (!exact(&n, sizeof(n))) {
        unsigned int x = 40, y = 24;
        if (!n || n > 8192 || exact(text, n)) return 5;
        text[n] = 0;
        for (unsigned int i = 0; i < 1024000; i++) canvas[i] = 0xff09111c;
        for (unsigned int i = 0; i < n; i++) {
            unsigned int ch = (unsigned char)text[i];
            if (ch == '\n') { x = 40; y += 16; continue; }
            if (y + 16 > 784) break;
            if (x + 8 > 1240) continue;
            if (ch < 32 || ch > 126) ch = '?';
            for (unsigned int row = 0; row < 16; row++)
                for (unsigned int col = 0; col < 8; col++)
                    if (font[ch * 16 + row] & (128U >> col))
                        canvas[(x + col) * 800 + 799 - y - row] = 0xffe0e6ed;
            x += 8;
        }
        memcpy((void *)fb, canvas, 4096000);
        if (write(STDOUT_FILENO, "1", 1) != 1) return 6;
    }
    munmap((void *)fb,4096000); close(fd); free(canvas);
    return 0;
}
