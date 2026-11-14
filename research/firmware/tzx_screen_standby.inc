/* SPDX-License-Identifier: GPL-2.0-or-later */
/* KMS owns the panel lifecycle. Keep the established rail/bias state while
 * standard DCS sleep stops panel scanning and the host's continuous video.
 */
static bool screen_panel_sleeping;
static unsigned long screen_panel_sleeps, screen_panel_wakes, screen_panel_errors;
static int screen_sleep_status = -1, screen_wake_status = -1;
static u32 screen_video_jump;
module_param(screen_panel_sleeping, bool, 0444);
module_param(screen_panel_sleeps, ulong, 0444);
module_param(screen_panel_wakes, ulong, 0444);
module_param(screen_panel_errors, ulong, 0444);
module_param(screen_sleep_status, int, 0444);
module_param(screen_wake_status, int, 0444);

static int screen_panel_resume(void)
{
    int ret = 0;
    mutex_lock(&display->update_lock);
    if (screen_panel_sleeping) {
        ret = tzx_panel_set_sleep(false, &screen_wake_status);
        if (ret) {
            screen_panel_errors++;
            drm_err(&display->drm, "panel wake failed %d; backlight stays off\n", ret);
        } else {
            /* LP packets overwrite the instruction jump table. Restore the
             * running video's table before the established HSC/HSD restart. */
            writel(screen_video_jump, dsi + 0x48);
            resume_video();
            screen_panel_sleeping = false;
            screen_panel_wakes++;
        }
    }
    mutex_unlock(&display->update_lock);
    return ret;
}

static void screen_panel_suspend(void)
{
    int ret;
    tzx_panel_blank(true);
    mutex_lock(&display->update_lock);
    if (!screen_panel_sleeping) {
        screen_video_jump = readl(dsi + 0x48);
        ret = pause_video();
        if (!ret) {
            ret = tzx_panel_set_sleep(true, &screen_sleep_status);
            if (!ret) {
                screen_panel_sleeping = true;
                screen_panel_sleeps++;
            }
        }
        if (ret) {
            screen_panel_errors++;
            drm_err(&display->drm, "panel sleep failed %d; recovering video with backlight off\n", ret);
            tzx_panel_set_sleep(false, &screen_wake_status);
            writel(screen_video_jump, dsi + 0x48);
            resume_video();
        }
    }
    memset(fb, 0, FB_BYTES);
    memset(screen_second, 0, FB_BYTES);
    dma_wmb();
    mutex_unlock(&display->update_lock);
}
