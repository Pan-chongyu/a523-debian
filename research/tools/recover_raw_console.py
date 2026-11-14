"""Finish an interrupted RAM-only head receiver with zero padding."""
import time
from fel_device import ROOT
import serial
data=bytearray()
with serial.Serial('COM11',115200,timeout=.02,write_timeout=5) as link:
    for n in range(1200):
        link.write(b'\0'*2048)
        time.sleep(.01)
        data.extend(link.read(link.in_waiting))
        if b'TZX_TRANSFER_DONE' in data:
            print('Receiver finished after', (n+1)*2048, 'padding bytes')
            break
    link.write(b'\x03\r\necho RAW_CONSOLE_RECOVERED; wc -c /tmp/initramfs-test.gz; stty -a\n')
    time.sleep(1)
    data.extend(link.read(32768))
print(data.decode(errors='replace')[-4000:])
