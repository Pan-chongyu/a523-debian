import gzip,hashlib,io,json,os,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flasher.core import make_gpt,verify_gpt,flash_image,validate_manifest,sha_file
from flasher.fel import Fel

class InstallerTests(unittest.TestCase):
    def test_compact_five_gib_image_gpt(self):
        sectors=5*1024**3//512;primary,secondary=make_gpt(sectors)
        self.assertTrue(verify_gpt(primary))
        self.assertEqual(struct.unpack_from('<Q',secondary[-512:],24)[0],sectors-1)
        self.assertEqual(struct.unpack_from('<Q',secondary,128+40)[0],sectors-34)
    def test_gpt_primary_and_secondary_crc_and_root_boundary(self):
        sectors=244318208;primary,secondary=make_gpt(sectors)
        self.assertTrue(verify_gpt(primary));header=bytearray(secondary[-512:])
        checksum=struct.unpack_from('<I',header,16)[0];struct.pack_into('<I',header,16,0)
        import zlib
        self.assertEqual(zlib.crc32(header[:92]),checksum)
        self.assertEqual(struct.unpack_from('<Q',secondary,128+40)[0],sectors-34)
        self.assertEqual(struct.unpack_from('<Q',header,24)[0],sectors-1)
    def test_traversal_manifest_rejected(self):
        manifest=dict(format='a523-debian-release-v1',board_profile='tzx-p30a523-20t5g-lpddr3-4g-uem128',
            emmc_sectors=244318208,files={'image':dict(name='../bad',bytes=1,sha256='0'*64)})
        with self.assertRaises(ValueError):validate_manifest(manifest)
    def test_bad_compressed_hash_never_opens_target(self):
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'image.gz';image.write_bytes(b'bad')
            with self.assertRaises(ValueError):flash_image(image,Path(folder)/'target',dict(emmc_sectors=244318208,
                files={'image':dict(name='image.gz',bytes=3,sha256='0'*64)}),244318208)
            self.assertFalse((Path(folder)/'target').exists())
    def test_verified_write_and_gpt_expand(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'image.gz';target=root/'target'
            data=bytearray(8*1024*1024);data[4*1024*1024:]=b'Z'*(4*1024*1024)
            primary,secondary=make_gpt(16777216);data[:len(primary)]=primary;data[-len(secondary):]=secondary
            with gzip.open(image,'wb') as output:output.write(data)
            # Use a small simulated device for I/O. The separate GPT test
            # verifies actual128GB boundary calculations without allocation.
            sectors=32768
            with target.open('wb') as output:output.truncate(sectors*512)
            manifest=dict(emmc_sectors=sectors,image_uncompressed_bytes=len(data),
                image_uncompressed_sha256=hashlib.sha256(data).hexdigest(),
                files={'image':dict(name=image.name,bytes=image.stat().st_size,sha256=sha_file(image))})
            with patch('flasher.core.make_gpt',return_value=make_gpt(244318208)):
                flash_image(image,target,manifest,sectors)
            with target.open('rb') as output:
                self.assertTrue(verify_gpt(output.read(34*512)))
                output.seek(4*1024*1024);self.assertEqual(output.read(1024),b'Z'*1024)
                output.seek((sectors-1)*512);self.assertEqual(output.read(8),b'EFI PART')
    def test_uncompressed_digest_failure_does_not_commit_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'image.gz';target=root/'target'
            with gzip.open(image,'wb') as output:output.write(b'A'*(8*1024*1024))
            with target.open('wb') as output:output.write(b'ORIGINAL');output.truncate(16*1024*1024)
            m=dict(emmc_sectors=244318208,image_uncompressed_bytes=8*1024*1024,image_uncompressed_sha256='0'*64,
                files={'image':dict(name=image.name,bytes=image.stat().st_size,sha256=sha_file(image))})
            with self.assertRaises(ValueError):flash_image(image,target,m,244318208)
            with target.open('rb') as output:self.assertEqual(output.read(8),b'ORIGINAL')
    def test_wrong_fel_card_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            helper=Path(folder)/'helper';helper.write_bytes(b'\0'*16);fel=Fel(helper)
            info=bytearray(528);info[:16]=bytes.fromhex('ffffffffffffffffffffffffffffffff')
            struct.pack_into('<I',info,228,244318208)
            with patch.object(fel,'operation'),patch.object(fel,'read_raw',return_value=bytes(info)):
                with self.assertRaises(ValueError):fel.identify()
            self.assertIsNone(fel.cid)

if __name__=='__main__':unittest.main()
