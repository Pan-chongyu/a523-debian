"""Decode the optional packed abort record without inventing omitted bits."""
def decode_abort_record(words):
    metadata, far_low, detail = words
    if metadata & 0xfe000000 != 0xd6000000:
        return None
    prefix = (detail >> 8) & 15
    prefixes = (0x000000, 0xffff00, 0xffff80, 0xfffffd, 0xffffff)
    far = far_low | ((detail & 255) << 32)
    esr = ((detail >> 12) & 63) | (((detail >> 18) & 63) << 26)
    esr |= (((detail >> 24) & 127) << 6) | (((detail >> 31) & 1) << 25)
    if prefix < len(prefixes):
        far |= prefixes[prefix] << 40
    return {'valid_signature': True, 'reason_code': 7,
        'reason': 'kernel_data_abort_pc_far_esr', 'cpu': (metadata >> 22) & 7,
        'fault_pc': hex(0xffff800080000000 + ((metadata & 0x3fffff) << 2)),
        'fault_far': hex(far) if prefix < len(prefixes) else None,
        'fault_far_low40': hex(far & ((1 << 40)-1)),
        'fault_far_complete': prefix < len(prefixes),
        'fault_esr_preserved_bits': hex(esr), 'fault_esr_preserved_mask': '0xfe001fff',
        'fault_exception_class': (esr >> 26) & 63, 'fault_status_code': esr & 63,
        'fault_write': bool(esr & 64), 'fault_address_invalid': bool(esr & 1024),
        'matches_last_cookie': False}
