"""Port the pinned Radxa SDIO driver to the locally built Linux 7.3 API.

Run against a fresh isolated source copy; no upstream checkout is modified.
These modules are candidates until tested on the board's actual SDIO device.
"""
from pathlib import Path
import re

port=Path('/opt/a523-debian-20261109/radxa-aic8800-port')
for path in [*port.rglob('*.c'),*port.rglob('*.h')]:
    old=path.read_text(errors='surrogateescape')
    new=old.replace('from_timer(', 'timer_container_of(')
    new=new.replace('del_timer_sync(', 'timer_delete_sync(').replace('del_timer(', 'timer_delete(')
    new=new.replace('<asm/unaligned.h>', '<linux/unaligned.h>')
    new=new.replace('in_irq()', 'in_hardirq()')
    new=re.sub(r'MODULE_IMPORT_NS\((\w+)\)',r'MODULE_IMPORT_NS("\1")',new)
    if 'strncpy(' in new:new=new.replace('strncpy(', 'strscpy(')
    if 'vfree(' in new and '#include <linux/vmalloc.h>' not in new:
        new='#include <linux/vmalloc.h>\n'+new
    new=new.replace('mgmt->u.action.u.tdls_discover_resp','mgmt->u.action.tdls_discover_resp')
    new=new.replace('mgmt->u.action.tdls_discover_resp.action_code','mgmt->u.action.action_code')
    new=re.sub(r'cfg80211_(new_sta|del_sta)\(([^,]+),',
               r'cfg80211_\1((\2)->ieee80211_ptr,',new)
    new=re.sub(r'(cfg80211_rx_(?:spurious_frame|unexpected_4addr_frame)\([^;]+?),\s*(GFP_\w+)\)',
               r'\1, -1, \2)',new)
    new=re.sub(r'(cfg80211_probe_status\([^,]+,[^,]+,[^,]+),\s*([01]),\s*0,\s*false,\s*(GFP_\w+)\)',
               r'\1, -1, \2, 0, false, \3)',new)
    if path.name=='rwnx_wakelock.c':
        new=new.replace('ws = wakeup_source_create(name);\n\twakeup_source_add(ws);',
                        'ws = wakeup_source_register(NULL, name);')
        new=new.replace('wakeup_source_remove(ws);\n\twakeup_source_destroy(ws);',
                        'wakeup_source_unregister(ws);')
    if path.name=='rwnx_defs.h':new=new.replace('u32 roc_cookie_cnt;', 'u64 roc_cookie_cnt;')
    if path.name=='rwnx_tx.h':new=new.replace('struct rwnx_sw_txhdr {', 'struct rwnx_sw_txhdr {\n\tu64 cfg_cookie;')
    if path.name=='rwnx_tx.c':
        new=new.replace('*cookie = (unsigned long)skb;', '/* Cookie is supplied by cfg80211 in Linux 7. */')
        begin=new.index('int rwnx_start_mgmt_xmit(') if 'int rwnx_start_mgmt_xmit(' in new else new.index('rwnx_start_mgmt_xmit(')
        before,section=new[:begin],new[begin:]
        section=section.replace('sw_txhdr->headroom = headroom;',
                                'sw_txhdr->headroom = headroom;\n\tsw_txhdr->cfg_cookie = *cookie;',1)
        section=section.replace('(unsigned long)skb,\n', 'sw_txhdr->cfg_cookie,\n')
        new=before+section
    if new!=old:path.write_text(new,errors='surrogateescape')

p=port/'aic8800_fdrv/rwnx_main.c'
t=p.read_text()
wrappers=[]
def wrap(name,params,args,extra=''):
    wrappers.append(f'''static int aic7_{name}(struct wiphy *wiphy, struct wireless_dev *wdev{params})
{{
    if (!wdev || !wdev->netdev) return -EOPNOTSUPP;
    {extra}
    return rwnx_cfg80211_{name}(wiphy, wdev->netdev{args});
}}
''')
for op in ('add_key','del_key'):
    more=', struct key_params *params' if op=='add_key' else ''
    wrap(op,', int link_id, u8 key_index, bool pairwise, const u8 *mac_addr'+more,
         ', link_id, key_index, pairwise, mac_addr'+(', params' if more else ''),
         'if (link_id > 0) return -EOPNOTSUPP;')
wrap('get_key',', int link_id, u8 key_index, bool pairwise, const u8 *mac_addr, void *cookie, void (*callback)(void *, struct key_params *)',
     ', link_id, key_index, pairwise, mac_addr, cookie, callback')
wrap('set_default_mgmt_key',', int link_id, u8 key_index',', link_id, key_index')
wrap('add_station',', const u8 *mac, struct station_parameters *params',', mac, params')
wrap('del_station_compat',', struct station_del_parameters *params',', params')
wrap('change_station',', const u8 *mac, struct station_parameters *params',', mac, params')
wrap('get_station',', const u8 *mac, struct station_info *sinfo',', mac, sinfo')
wrap('dump_station',', int idx, u8 *mac, struct station_info *sinfo',', idx, mac, sinfo')
wrappers.append('''static int aic7_mgmt_tx(struct wiphy *wiphy, struct wireless_dev *wdev,
    struct cfg80211_mgmt_tx_params *params, u64 cookie)
{ return rwnx_cfg80211_mgmt_tx(wiphy, wdev, params, &cookie); }
static int aic7_remain_on_channel(struct wiphy *wiphy, struct wireless_dev *wdev,
    struct ieee80211_channel *chan, unsigned duration, u64 cookie, const u8 *addr)
{
    struct rwnx_hw *hw=wiphy_priv(wiphy);
    if (addr) return -EOPNOTSUPP;
    if (hw->roc_elem) return -EBUSY;
    hw->roc_cookie_cnt=cookie;
    return rwnx_cfg80211_remain_on_channel_(wiphy,wdev,chan,duration,&cookie,false);
}
static int aic7_set_monitor_channel(struct wiphy *wiphy, struct net_device *dev,
    struct cfg80211_chan_def *chandef)
{ return rwnx_cfg80211_set_monitor_channel(wiphy,chandef); }
static int aic7_set_wiphy_params(struct wiphy *wiphy, int radio_idx, u32 changed)
{ if (radio_idx > 0) return -EOPNOTSUPP; return rwnx_cfg80211_set_wiphy_params(wiphy,changed); }
static int aic7_set_tx_power(struct wiphy *wiphy, struct wireless_dev *wdev, int link_id,
    enum nl80211_tx_power_setting type, int mbm)
{ if (link_id > 0) return -EOPNOTSUPP; return rwnx_cfg80211_set_tx_power(wiphy,wdev,type,mbm); }
static int aic7_get_tx_power(struct wiphy *wiphy, struct wireless_dev *wdev, int link_id,
    unsigned radio_idx, int *dbm)
{ if (link_id > 0 || radio_idx > 0) return -EOPNOTSUPP; return rwnx_cfg80211_get_tx_power(wiphy,wdev,dbm); }
''')
t=t.replace('static struct cfg80211_ops rwnx_cfg80211_ops = {',
            '\n'.join(wrappers)+'\nstatic struct cfg80211_ops rwnx_cfg80211_ops = {')
ops=['add_key','get_key','del_key','set_default_mgmt_key','add_station',
     'del_station_compat','change_station','get_station','dump_station','mgmt_tx',
     'remain_on_channel','set_monitor_channel','set_wiphy_params','set_tx_power','get_tx_power']
for name in ops:
    t=re.sub(r'(=\s*)rwnx_cfg80211_'+name+r'(\s*[,;])',r'\1aic7_'+name+r'\2',t)
t=re.sub(r'^\s*\.probe_client = rwnx_cfg80211_probe_client,\n','\n',t,flags=re.M)
p.write_text(t)
