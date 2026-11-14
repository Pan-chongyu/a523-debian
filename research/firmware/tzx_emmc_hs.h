/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TZX_EMMC_HS_H
#define TZX_EMMC_HS_H
struct mmc_card;
struct mmc_host;
int mmc_tzx_switch_mode(struct mmc_card *card,unsigned int mode,unsigned int clock);
int sunxi_mmc_tzx_mode(struct mmc_host *mmc,unsigned int mode,unsigned int clock);
#endif
