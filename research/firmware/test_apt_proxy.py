import urllib.request
handler = urllib.request.ProxyHandler({'https': 'http://192.168.77.1:3142'})
opener = urllib.request.build_opener(handler)
with opener.open('https://deb.debian.org/debian/dists/trixie/InRelease', timeout=25) as r:
    print(r.status, r.read(120).decode())
