"""Resize the user's PNG, losslessly encode its pixels, and sign the boot splash."""
import hashlib,json,struct,subprocess,zlib
from pathlib import Path
from PIL import Image
from make_toc0 import build
root=Path(__file__).resolve().parents[1]
out=root/'build/boot-logo';out.mkdir(exist_ok=True)
source=Path(r'C:/Users/pan75/Desktop/canvas-image-image-1792510098174-8icke.png')
image=Image.open(source).convert('RGBA')
(out/'source.png').write_bytes(source.read_bytes())
image.thumbnail((720,720),Image.Resampling.LANCZOS)
canvas=Image.new('RGBA',(1280,800),(0,0,0,255))
canvas.alpha_composite(image,((1280-image.width)//2,(800-image.height)//2))
canvas.convert('RGB').save(out/'splash-preview.png')
native=canvas.transpose(Image.Transpose.ROTATE_270)
data=native.tobytes('raw','BGRA');(out/'splash-native.bgra').write_bytes(data)
pixels=struct.unpack('<1024000I',data)
encoded=bytearray();n=len(pixels);i=0;literal=[]
def flush():
    if literal:
        encoded.extend(struct.pack('<I',len(literal)));encoded.extend(struct.pack('<%dI'%len(literal),*literal));literal.clear()
while i<n:
    j=i+1
    while j<n and pixels[j]==pixels[i]:j+=1
    if j-i>=3:
        flush();encoded.extend(struct.pack('<II',0x80000000|(j-i),pixels[i]));i=j
    else:
        literal.extend(pixels[i:j]);i=j
flush()
(out/'splash.rle').write_bytes(encoded)
assert len(encoded)%4==0 and len(encoded)<0x3fe000
config=dict(LOGO_CODE_SPACE=8192,LOGO_RLE_BYTES=len(encoded),LOGO_LBA=49152,
            LOGO_PAYLOAD_BYTES=8192+((len(encoded)+511)&~511),LOGO_PAYLOAD_CRC=0,LOGO_ENTRY=0)
def header():
    (out/'logo_config.h').write_text('/* generated */\n'+''.join('#define %s 0x%xU\n'%(k,v) for k,v in config.items()),newline='\n')
def compile_code():
    subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh','/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_logo.sh'],check=True)
header();compile_code()
code=(out/'logo.bin').read_bytes();assert len(code)<=8192
payload=code+bytes(8192-len(code))+encoded
payload+=bytes(-len(payload)%512)
config['LOGO_PAYLOAD_CRC']=zlib.crc32(payload)
config['LOGO_ENTRY']=struct.unpack_from('<I',(out/'logo.elf').read_bytes(),24)[0]
header();compile_code()
assert code==(out/'logo.bin').read_bytes(), 'SRAM-only constants changed the external executable'
loader=(out/'loader.bin').read_bytes();assert len(loader)<=0x4f080-0x4e900
base=(root/'build/boot-cpu-performance/loader.bin').read_bytes()
oldtoc=(root/'build/boot-cpu-performance/loader.toc0').read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(oldtoc)=='367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c'
new=bytearray(base);patches=[]
def patch(address,was,value,why):
    offset=address-0x44000;assert struct.unpack_from('<I',new,offset)[0]==was,(hex(address),hex(was))
    struct.pack_into('<I',new,offset,value);patches.append(dict(address=address,old=was,new=value,reason=why))
entry=struct.unpack_from('<I',(out/'loader.elf').read_bytes(),24)[0]
old=struct.unpack_from('<I',base,0x4a0)[0]
patch(0x444a0,old,0xeb000000|(((entry-0x444a0-8)//4)&0xffffff),'optional post-training splash wrapper')
# Identify the exact MOV before the STR to HOST+0x2f8 using disassembly.
dis=(root/'build/boot-panel-early-v2/panel-hook.disassembly.txt').read_text()
lines=dis.splitlines();fixed=[]
for i,line in enumerate(lines):
    if 'e3a030ff' in line and any('#760]' in x for x in lines[i+1:i+5]):fixed.append(int(line.split(':')[0],16))
assert len(fixed)==1, fixed
# MOV r3,BIT(28), with RGB=0: fixed black replaces the streaming source.
patch(fixed[0],0xe3a030ff,0xe3a03201,'stream fixed black while DRAM initializes')
new+=bytes(0x4e900-0x44000-len(new))+loader
assert len(new)+0xf80<=49152
(out/'payload.bin').write_bytes(payload);(out/'sram-loader.bin').write_bytes(new)
build(bytes(new),0x44000,out/'loader.toc0')
manifest=json.loads((out/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=sha(oldtoc),loader_sha256=sha(new),patches=patches,
    source_path=str(source),source_sha256=sha(source.read_bytes()),source_size=[1254,1254],
    canvas_size=[1280,800],orientation='right',native_size=[800,1280],logo_size=list(image.size),
    native_bgra_sha256=sha(data),rle_sha256=sha(encoded),rle_bytes=len(encoded),
    payload_sha256=sha(payload),payload_bytes=len(payload),payload_lba=49152,
    payload_crc32=config['LOGO_PAYLOAD_CRC'],payload_entry=config['LOGO_ENTRY'],code_bytes=len(code),
    sram_wrapper_bytes=len(loader),framebuffer='0x42400000',RCQ='0x42800000',
    required_reserved_range=['0x42000000','0x42900000'],
    optional_failure_continues_boot=True,ARM_emulation_verified=False,hardware_boot_verified=False)
(out/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_LOGO_IMAGE_BUILT',manifest['image_sha256'],len(payload),len(loader),flush=True)
