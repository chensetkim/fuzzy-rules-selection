/*
 * DM-2H-FuzzRID — T-HFIS hierarchical fuzzy engine header
 * Implementation: apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.c
 */

#ifndef FUZZRID_FUZZY_HFS_H_
#define FUZZRID_FUZZY_HFS_H_

#include <stdint.h>

/*
 * T-HFIS: hierarchical replacement for Algorithm 2.
 * Same contract as fuzzrid_fuzzy_infer_ac(): v1..v7 each 0-100,
 * returns AC 0-100.
 */
uint8_t fuzzrid_fuzzy_infer_ac_hfs(uint8_t v1, uint8_t v2, uint8_t v3,
                                   uint8_t v4, uint8_t v5, uint8_t v6,
                                   uint8_t v7);

/*
 * Extended form exposing the layer-1 intermediates for per-branch
 * attribution logging.  Any out-pointer may be NULL.
 */
uint8_t fuzzrid_fuzzy_infer_ac_hfs_x(uint8_t v1, uint8_t v2, uint8_t v3,
                                     uint8_t v4, uint8_t v5, uint8_t v6,
                                     uint8_t v7, uint8_t *ra_out,
                                     uint8_t *si_out, uint8_t *cx_out);

#endif /* FUZZRID_FUZZY_HFS_H_ */
