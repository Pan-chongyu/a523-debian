"""Create a local authentication key for administering the connected tablet."""
import subprocess
from fel_device import ROOT
key=ROOT/'private/tzx-host-ed25519'
if not key.exists():
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','tzx-a523-local-admin','-f',str(key)],check=True)
print('Tablet administration key is stored in the private directory.')
