// SPDX-License-Identifier: GPL-2.0-only
/* Board-specific bring-up driver: paged GSL3670 download, verified on P30.
 * Firmware electrode tuning and coordinate calibration remain provisional.
 */
#include <linux/module.h>
#include <linux/i2c.h>
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/gpio/consumer.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/input/touchscreen.h>
#include <linux/interrupt.h>
#include <linux/regulator/consumer.h>
#include <linux/unaligned.h>

struct tzx_touch {
    struct i2c_client *client;
    struct gpio_desc *reset;
    struct input_dev *input;
    struct touchscreen_properties prop;
    struct input_mt_pos pos[11];
    int slots[11];
    spinlock_t stats_lock;
    u32 frames,read_errors,invalid_frames,clamped_points,max_contacts;
    u8 last_packet[48];
};
static int tzx_write(struct tzx_touch *ts,u8 reg,const void *buf,size_t len)
{
    u8 packet[129];int ret;
    if(len>128)return -EINVAL;
    packet[0]=reg;memcpy(packet+1,buf,len);
    ret=i2c_master_send(ts->client,packet,len+1);
    return ret==len+1?0:ret<0?ret:-EIO;
}
static int tzx_byte(struct tzx_touch *ts,u8 reg,u8 val)
{
    int ret=tzx_write(ts,reg,&val,1);msleep(15);return ret;
}
static int tzx_read(struct tzx_touch *ts,u8 reg,void *buf,size_t len)
{
    struct i2c_msg msgs[]={
        {.addr=ts->client->addr,.len=1,.buf=&reg},
        {.addr=ts->client->addr,.flags=I2C_M_RD,.len=len,.buf=buf},
    };
    int ret=i2c_transfer(ts->client->adapter,msgs,2);
    return ret==2?0:ret<0?ret:-EIO;
}
static void tzx_reset(struct tzx_touch *ts)
{
    gpiod_set_value_cansleep(ts->reset,0);msleep(20);
    gpiod_set_value_cansleep(ts->reset,1);msleep(30);
}
static void tzx_stop(void *ptr)
{
    struct tzx_touch *ts=ptr;
    gpiod_set_value_cansleep(ts->reset,0);
}
static int tzx_start(struct tzx_touch *ts)
{
    const struct firmware *fw;const char *name;int ret;u8 page[128];
    u32 zero=0;u8 status[4],id[4];
    ret=device_property_read_string(&ts->client->dev,"firmware-name",&name);
    if(ret)return ret;
    ret=request_firmware(&fw,name,&ts->client->dev);if(ret)return ret;
    if(fw->size==0||fw->size%(33*8)){ret=-EINVAL;goto done;}
    tzx_reset(ts);
    ret=tzx_read(ts,0xfc,id,4);if(ret)goto done;
    dev_info(&ts->client->dev,"chip ID %08x\n",get_unaligned_le32(id));
    if((ret=tzx_byte(ts,0x88,1))||(ret=tzx_byte(ts,0xe4,4))||
       (ret=tzx_byte(ts,0xe0,0)))goto done;
    tzx_reset(ts);
    if((ret=tzx_byte(ts,0xe4,4))||(ret=tzx_write(ts,0xbc,&zero,4)))goto done;
    for(size_t i=0;i<fw->size;i+=33*8){
        const u8 *records=fw->data+i;u32 p=get_unaligned_le32(records+4);
        if(get_unaligned_le32(records)!=0xf0||p>0xef){ret=-EINVAL;goto done;}
        for(unsigned j=0;j<32;j++){
            if(get_unaligned_le32(records+(j+1)*8)!=j*4){ret=-EINVAL;goto done;}
            memcpy(page+j*4,records+(j+1)*8+4,4);
        }
        u8 val=p;
        if((ret=tzx_write(ts,0xf0,&val,1))||(ret=tzx_write(ts,0,page,128)))goto done;
    }
    ret=tzx_byte(ts,0xe0,0);if(ret)goto done;
    msleep(100);
    ret=tzx_read(ts,0xb0,status,4);if(ret)goto done;
    if(get_unaligned_le32(status)!=0x5a5a5a5a){ret=-EIO;goto done;}
    dev_info(&ts->client->dev,"paged firmware running; calibration is provisional\n");
done:
    release_firmware(fw);return ret;
}
static ssize_t stats_show(struct device *dev,struct device_attribute *attr,char *buf)
{
    struct tzx_touch *ts=dev_get_drvdata(dev);
    unsigned long flags;u32 frames,errors,invalid,clamped,contacts;u8 last[48];
    spin_lock_irqsave(&ts->stats_lock,flags);
    frames=ts->frames;errors=ts->read_errors;invalid=ts->invalid_frames;
    clamped=ts->clamped_points;contacts=ts->max_contacts;
    memcpy(last,ts->last_packet,sizeof(last));
    spin_unlock_irqrestore(&ts->stats_lock,flags);
    return sysfs_emit(buf,"frames=%u read_errors=%u invalid_frames=%u clamped_points=%u max_contacts=%u last_packet=%*phN\n",
                      frames,errors,invalid,clamped,contacts,(int)sizeof(last),last);
}
static DEVICE_ATTR_RO(stats);
static struct attribute *tzx_attrs[]={&dev_attr_stats.attr,NULL};
static const struct attribute_group tzx_stats_group={.attrs=tzx_attrs};

static irqreturn_t tzx_irq(int irq,void *ptr)
{
    struct tzx_touch *ts=ptr;u8 data[48];unsigned count;unsigned long flags;
    if(tzx_read(ts,0x80,data,sizeof(data))){
        spin_lock_irqsave(&ts->stats_lock,flags);ts->read_errors++;
        spin_unlock_irqrestore(&ts->stats_lock,flags);return IRQ_HANDLED;
    }
    count=data[0]&0xf;
    spin_lock_irqsave(&ts->stats_lock,flags);
    ts->frames++;memcpy(ts->last_packet,data,sizeof(data));
    ts->max_contacts=max(ts->max_contacts,count);
    if(count>11)ts->invalid_frames++;
    spin_unlock_irqrestore(&ts->stats_lock,flags);
    if(count>11)return IRQ_HANDLED;
    for(unsigned i=0;i<count;i++){
        const u8 *p=data+4+i*4;
        unsigned x=get_unaligned_le16(p+2)&0xfff,y=get_unaligned_le16(p)&0xfff;
        /* Keep provisional firmware edge values representable, especially
         * before an inversion (unsigned subtraction must not underflow). */
        if(x>ts->prop.max_x||y>ts->prop.max_y){
            spin_lock_irqsave(&ts->stats_lock,flags);ts->clamped_points++;
            spin_unlock_irqrestore(&ts->stats_lock,flags);
        }
        touchscreen_set_mt_pos(&ts->pos[i],&ts->prop,
            min(x,ts->prop.max_x),min(y,ts->prop.max_y));
    }
    input_mt_assign_slots(ts->input,ts->slots,ts->pos,count,0);
    for(unsigned i=0;i<count;i++){
        input_mt_slot(ts->input,ts->slots[i]);
        input_mt_report_slot_state(ts->input,MT_TOOL_FINGER,true);
        input_report_abs(ts->input,ABS_MT_POSITION_X,ts->pos[i].x);
        input_report_abs(ts->input,ABS_MT_POSITION_Y,ts->pos[i].y);
    }
    input_mt_sync_frame(ts->input);input_sync(ts->input);
    return IRQ_HANDLED;
}
static int tzx_probe(struct i2c_client *client)
{
    struct device *dev=&client->dev;struct tzx_touch *ts;int ret;
    if(client->irq<=0)return dev_err_probe(dev,-EINVAL,"Missing verified IRQ\n");
    ts=devm_kzalloc(dev,sizeof(*ts),GFP_KERNEL);if(!ts)return -ENOMEM;
    ts->client=client;spin_lock_init(&ts->stats_lock);i2c_set_clientdata(client,ts);
    /* The runtime registration helper is used only after the guarded test
     * script enables CLDO2. A normal DT binding still requires its supply. */
    if(!device_property_read_bool(dev,"tzx,externally-powered")){
        ret=devm_regulator_get_enable(dev,"avdd");if(ret)return ret;
    }
    ts->reset=devm_gpiod_get(dev,"power",GPIOD_OUT_LOW);
    if(IS_ERR(ts->reset))return PTR_ERR(ts->reset);
    ret=devm_add_action_or_reset(dev,tzx_stop,ts);if(ret)return ret;
    ret=tzx_start(ts);if(ret)return dev_err_probe(dev,ret,"Firmware initialization\n");
    ts->input=devm_input_allocate_device(dev);if(!ts->input)return -ENOMEM;
    ts->input->name="TZX GSL3670 candidate";
    ts->input->id.bustype=BUS_I2C;
    /* The packet's native X is the long axis. The firmware candidate's
     * portrait transform belongs in the touchscreen properties. */
    input_set_abs_params(ts->input,ABS_MT_POSITION_X,0,1647,0,0);
    input_set_abs_params(ts->input,ABS_MT_POSITION_Y,0,879,0,0);
    touchscreen_parse_properties(ts->input,true,&ts->prop);
    ret=input_mt_init_slots(ts->input,11,INPUT_MT_DIRECT|INPUT_MT_DROP_UNUSED|INPUT_MT_TRACK);
    if(ret)return ret;
    ret=input_register_device(ts->input);if(ret)return ret;
    ret=devm_device_add_group(dev,&tzx_stats_group);if(ret)return ret;
    return devm_request_threaded_irq(dev,client->irq,NULL,tzx_irq,
        IRQF_ONESHOT,dev_name(dev),ts);
}
static const struct of_device_id tzx_match[]={
    {.compatible="tzx,p30-gsl3670-candidate"},{}
};
MODULE_DEVICE_TABLE(of,tzx_match);
static const struct i2c_device_id tzx_ids[]={
    {"tzx-gsl3670"},{}
};
MODULE_DEVICE_TABLE(i2c,tzx_ids);
static struct i2c_driver tzx_driver={
    .driver={.name="tzx-gsl3670",.of_match_table=tzx_match},.probe=tzx_probe,
    .id_table=tzx_ids,
};
module_i2c_driver(tzx_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 GSL3670 paged firmware bring-up");
