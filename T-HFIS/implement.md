
Copy both files ```fuzzrid-fuzz-hfs.c``` and ```fuzzrid-fuzzy-hfs.h``` to folder ```apps/2h-fuzzrid```

1. In ```fuzzrid-fuzzy.c``` — add the include at the top, then call 
the function from inside the existing entry point:

```c
#include "apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.h"
```

```c

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
  /* existing R1..R18 body, unchanged */
  uint8_t w[19]; uint8_t z[19];
  /* other code */
#endif
}

```

2. In ```apps/2h-fuzzrid/Makefile.2h-fuzzrid``` — the new file must be compiled:

```
2h-fuzzrid_src += fuzzrid-fuzzy-hfs.c
```

3. In ```examples/2h-fuzzrid/Makefile``` — the switch:

```
CFLAGS += -DWITH_THFIS=1
```

then run cooja simulation.