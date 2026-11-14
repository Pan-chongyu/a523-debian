"""Check SHA padding boundaries and bounded reads against Python hashlib."""
import hashlib,pathlib,subprocess,sys,tempfile
exe=str(pathlib.Path(sys.argv[1]).resolve())
cases=0
with tempfile.TemporaryDirectory(prefix='tzx-sha-') as tmp:
    p=pathlib.Path(tmp)/'vector'
    for size in (0,1,55,56,63,64,65,127,128,129,65535,65536,65537):
        data=bytes(range(256))*(size//256)+bytes(range(size%256))
        p.write_bytes(data)
        actual=subprocess.check_output(['qemu-aarch64-static','-cpu','max',exe,str(p)],text=True).split()[0]
        assert actual==hashlib.sha256(data).hexdigest(),size
        cases+=1
    data=p.read_bytes()
    for offset,length in ((1,55),(123,4096),(65400,137)):
        actual=subprocess.check_output(['qemu-aarch64-static','-cpu','max',exe,str(p),str(offset),str(length)],text=True).split()[0]
        assert actual==hashlib.sha256(data[offset:offset+length]).hexdigest()
        cases+=1
print(f'ARM64 SHA256: {cases} independent boundary/region checks passed.')
