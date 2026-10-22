# Deploying a selected T-HFIS hierarchy in the firmware

`./run_thfis.sh` writes, for every split, a **complete** `fuzzrid-fuzzy-hfs.c` for the selected
hierarchy: `seed_<s>/primary/selected_rules.c` (knee) and `selected_rules_best_f1.c` (best-F1).
It contains the membership functions with the run's breakpoints, the integer Sugeno average and
the two entry points declared in `methods/thfis/c/fuzzrid-fuzzy-hfs.h`, and is bit-exact with the
Python model under `ARITH=int`. Do not paste rule blocks into another file by hand.

1. Copy the chosen file to `apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.c`, and
   `methods/thfis/c/fuzzrid-fuzzy-hfs.h` to `apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.h`.

2. In `fuzzrid-fuzzy.c`, include the header and call the function from the existing entry point:

```c
#include "apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.h"

uint8_t
fuzzrid_fuzzy_infer_ac(uint8_t v1, uint8_t v2, uint8_t v3,
                       uint8_t v4, uint8_t v5, uint8_t v6, uint8_t v7)
{
#if WITH_THFIS
  uint8_t ra, si, cx;
  uint8_t ac = fuzzrid_fuzzy_infer_ac_hfs_x(v1, v2, v3, v4, v5, v6, v7,
                                            &ra, &si, &cx);
  PRINTF("[HFS] ra=%u si=%u cx=%u ac=%u\n", ra, si, cx, ac);
  return ac;
#else
  /* existing flat body, unchanged */
#endif
}
```

3. In `apps/2h-fuzzrid/Makefile.2h-fuzzrid`, compile the new file:

```
2h-fuzzrid_src += fuzzrid-fuzzy-hfs.c
```

4. In `examples/2h-fuzzrid/Makefile`, enable it:

```
CFLAGS += -DWITH_THFIS=1
```

Then rebuild and run the Cooja simulation. The membership functions in the generated file follow
`MF_HIGH` of the run (`config.txt`); `fuzzrid-fuzzy.c`'s own `mu_*` are not used by T-HFIS.
