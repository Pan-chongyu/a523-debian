"""Apply explicit Linux 7 API updates to the isolated AIC8800 source copy."""
from pathlib import Path
import re
port=Path('/opt/a523-debian-20261109/aic8800-port')
for path in list(port.rglob('*.c'))+list(port.rglob('*.h')):
    old=path.read_text(errors='surrogateescape')
    new=old.replace('from_timer(', 'timer_container_of(')
    new=new.replace('del_timer_sync(', 'timer_delete_sync(')
    new=new.replace('del_timer(', 'timer_delete(')
    new=new.replace('<asm/unaligned.h>', '<linux/unaligned.h>')
    new=new.replace('<linux/unaligned/le_byteshift.h>', '<linux/unaligned.h>')
    # The Android 5.15 backports already use link-based cfg80211 objects.
    # Mainline 7 also requires those branches, without Android vendor hooks.
    new=re.sub(r'^(#(?:if|elif) [^\n]*&& defined\(KERNEL_AOSP\))$',
               r'\1 || LINUX_VERSION_CODE >= KERNEL_VERSION(6, 1, 0)',new,flags=re.M)
    if path.name=='rwnx_wakelock.c':
        new=new.replace('ws = wakeup_source_create(name);\n\twakeup_source_add(ws);',
                        'ws = wakeup_source_register(NULL, name);')
        new=new.replace('wakeup_source_remove(ws);\n\twakeup_source_destroy(ws);',
                        'wakeup_source_unregister(ws);')
    if path.name=='rwnx_msg_tx.c':
        new=new.replace('strncpy(req->name, name, sizeof(req->name));',
                        'strscpy(req->name, name, sizeof(req->name));')
    if new!=old:path.write_text(new,errors='surrogateescape')
