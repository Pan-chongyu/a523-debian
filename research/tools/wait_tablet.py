"""Wait for SSH on the tablet's dedicated USB link, without changing it."""
import socket,time
until=time.monotonic()+180
while time.monotonic()<until:
    try:
        with socket.create_connection(('192.168.77.2',22),timeout=1) as connection:
            banner=connection.recv(200)
            if banner.startswith(b'SSH-2.0-OpenSSH'):
                print('Tablet SSH is ready.');break
    except OSError:pass
    time.sleep(2)
else:raise TimeoutError('Tablet SSH did not return within 180 seconds')
