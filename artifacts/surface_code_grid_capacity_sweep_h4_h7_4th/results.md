# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 48 | 44 | 4 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H4

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 96,389,427,875 | 0 (0.00%) |
| p1e-5_aware_8x8 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 94,975,266,191 | 0 (0.00%) |
| p1e-5_auto_10x10 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,402,238 | 0 (0.00%) | 100,574,405,347 | 0 (0.00%) |
| p1e-5_aware_10x10 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 94,366,965,004 | 0 (0.00%) |
| p1e-5_auto_12x12 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 103,717,588,182 | 0 (0.00%) |
| p1e-5_aware_12x12 | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 94,976,720,280 | 0 (0.00%) |
| p1e-2_auto_8x8 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,858,646,535 | 0 (0.00%) |
| p1e-2_aware_8x8 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,476,078,999 | 0 (0.00%) |
| p1e-2_auto_10x10 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 20,026,227,559 | 0 (0.00%) |
| p1e-2_aware_10x10 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,322,634,344 | 0 (0.00%) |
| p1e-2_auto_12x12 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,711,463 | 0 (0.00%) | 21,201,361,064 | 0 (0.00%) |
| p1e-2_aware_12x12 | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,476,450,721 | 0 (0.00%) |

### H5

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,571,030 | 0 (0.00%) | 264,804,986,490 | 0 (0.00%) |
| p1e-5_aware_8x8 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 263,308,356,795 | 0 (0.00%) |
| p1e-5_auto_10x10 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,717,055 | 0 (0.00%) | 277,174,287,225 | 0 (0.00%) |
| p1e-5_aware_10x10 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,411,665,945 | 0 (0.00%) |
| p1e-5_auto_12x12 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,522,355 | 0 (0.00%) | 282,139,205,370 | 0 (0.00%) |
| p1e-5_aware_12x12 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 263,310,391,410 | 0 (0.00%) |
| p1e-2_auto_8x8 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 51,444,091,545 | 0 (0.00%) |
| p1e-2_aware_8x8 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 51,085,327,590 | 0 (0.00%) |
| p1e-2_auto_10x10 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 53,782,623,510 | 0 (0.00%) |
| p1e-2_aware_10x10 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 50,703,199,635 | 0 (0.00%) |
| p1e-2_auto_12x12 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 55,087,162,185 | 0 (0.00%) |
| p1e-2_aware_12x12 | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 51,080,693,730 | 0 (0.00%) |

### H6

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | 4th(new_2) | failed | 11,605 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-5_aware_8x8 | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,857,055 | 0 (0.00%) | 799,057,830,285 | 0 (0.00%) |
| p1e-5_auto_10x10 | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,108,240,020 | 0 (0.00%) | 818,978,625,135 | 0 (0.00%) |
| p1e-5_aware_10x10 | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,845,450 | 0 (0.00%) | 786,525,439,920 | 0 (0.00%) |
| p1e-5_auto_12x12 | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,880,265 | 0 (0.00%) | 829,919,749,505 | 0 (0.00%) |
| p1e-5_aware_12x12 | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,787,425 | 0 (0.00%) | 789,277,519,250 | 0 (0.00%) |
| p1e-2_auto_8x8 | 4th(new_2) | failed | 11,605 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-2_aware_8x8 | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,552,650 | 0 (0.00%) | 139,792,588,265 | 0 (0.00%) |
| p1e-2_auto_10x10 | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,204,500 | 0 (0.00%) | 146,077,809,845 | 0 (0.00%) |
| p1e-2_aware_10x10 | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,158,080 | 0 (0.00%) | 139,825,848,195 | 0 (0.00%) |
| p1e-2_auto_12x12 | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,158,080 | 0 (0.00%) | 149,943,783,495 | 0 (0.00%) |
| p1e-2_aware_12x12 | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,158,080 | 0 (0.00%) | 140,667,744,525 | 0 (0.00%) |

### H7

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | 4th(new_2) | failed | 11,298 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-5_aware_8x8 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 111,379,864,260 | 0 (0.00%) | 1,921,860,491,586 | 0 (0.00%) |
| p1e-5_auto_10x10 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,100,304 | 0 (0.00%) | 1,743,496,536,516 | 0 (0.00%) |
| p1e-5_aware_10x10 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,232,466,600 | 0 (0.00%) | 1,684,993,379,790 | 0 (0.00%) |
| p1e-5_auto_12x12 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,224,953,430 | 0 (0.00%) | 1,775,973,032,946 | 0 (0.00%) |
| p1e-5_aware_12x12 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,224,896,940 | 0 (0.00%) | 1,700,644,894,620 | 0 (0.00%) |
| p1e-2_auto_8x8 | 4th(new_2) | failed | 11,298 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-2_aware_8x8 | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,688,549,674 | 0 (0.00%) | 303,460,834,110 | 0 (0.00%) |
| p1e-2_auto_10x10 | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,648,091,536 | 0 (0.00%) | 312,366,708,570 | 0 (0.00%) |
| p1e-2_aware_10x10 | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,657,638,346 | 0 (0.00%) | 298,540,792,368 | 0 (0.00%) |
| p1e-2_auto_12x12 | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,648,091,536 | 0 (0.00%) | 322,220,586,912 | 0 (0.00%) |
| p1e-2_aware_12x12 | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,648,091,536 | 0 (0.00%) | 299,447,965,278 | 0 (0.00%) |

## H4 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 5.79923e-05 | 4 | 0.00015936 | 10932.1 | 10,933 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | success | 8,900,380,372 | N/A | 8,900,369,439 | 96,389,427,875 | N/A | 2,018,231,800 | 1,899,586,884 | 60 | 20,280 | 13 |
| p1e-5_aware_8x8 | success | 8,900,380,372 | N/A | 8,900,369,439 | 94,975,266,191 | N/A | 2,018,231,800 | 1,899,586,884 | 60 | 20,280 | 13 |
| p1e-5_auto_10x10 | success | 8,900,402,238 | N/A | 8,900,369,439 | 100,574,405,347 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-5_aware_10x10 | success | 8,900,380,372 | N/A | 8,900,369,439 | 94,366,965,004 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-5_auto_12x12 | success | 8,900,380,372 | N/A | 8,900,369,439 | 103,717,588,182 | N/A | 2,018,231,800 | 1,899,586,884 | 140 | 47,320 | 13 |
| p1e-5_aware_12x12 | success | 8,900,380,372 | N/A | 8,900,369,439 | 94,976,720,280 | N/A | 2,018,231,800 | 1,899,586,884 | 140 | 47,320 | 13 |
| p1e-2_auto_8x8 | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,858,646,535 | N/A | 128,091,028 | 111,254,208 | 60 | 20,280 | 13 |
| p1e-2_aware_8x8 | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,476,078,999 | N/A | 128,091,028 | 111,254,208 | 60 | 20,280 | 13 |
| p1e-2_auto_10x10 | success | 1,600,700,530 | N/A | 1,600,689,597 | 20,026,227,559 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |
| p1e-2_aware_10x10 | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,322,634,344 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |
| p1e-2_auto_12x12 | success | 1,600,711,463 | N/A | 1,600,689,597 | 21,201,361,064 | N/A | 128,091,028 | 111,254,208 | 140 | 47,320 | 13 |
| p1e-2_aware_12x12 | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,476,450,721 | N/A | 128,091,028 | 111,254,208 | 140 | 47,320 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,816,375 | N/A | 60 | 20,280 | 13 | 184,600 | 173,748 |
| p1e-5_aware_8x8 | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,687,027 | N/A | 60 | 20,280 | 13 | 184,600 | 173,748 |
| p1e-5_auto_10x10 | success | 15 | 10,000 | 814,086 | N/A | 814,083 | 3 | 9,199,159 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-5_aware_10x10 | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,631,388 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-5_auto_12x12 | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 9,486,654 | N/A | 140 | 47,320 | 13 | 184,600 | 173,748 |
| p1e-5_aware_12x12 | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,687,160 | N/A | 140 | 47,320 | 13 | 184,600 | 173,748 |
| p1e-2_auto_8x8 | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,816,395 | N/A | 60 | 20,280 | 13 | 11,716 | 10,176 |
| p1e-2_aware_8x8 | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,781,403 | N/A | 60 | 20,280 | 13 | 11,716 | 10,176 |
| p1e-2_auto_10x10 | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,831,723 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |
| p1e-2_aware_10x10 | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,767,368 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |
| p1e-2_auto_12x12 | success | 15 | 10,000 | 146,411 | N/A | 146,409 | 2 | 1,939,208 | N/A | 140 | 47,320 | 13 | 11,716 | 10,176 |
| p1e-2_aware_12x12 | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,781,437 | N/A | 140 | 47,320 | 13 | 11,716 | 10,176 |

## H5 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 3.64607e-05 | 4 | 0.00015936 | 9734.55 | 9,735 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | success | 20,660,571,030 | N/A | 20,660,249,775 | 264,804,986,490 | N/A | 4,632,944,910 | 4,393,035,570 | 60 | 27,000 | 15 |
| p1e-5_aware_8x8 | success | 20,660,502,885 | N/A | 20,660,249,775 | 263,308,356,795 | N/A | 4,632,944,910 | 4,393,035,570 | 60 | 27,000 | 15 |
| p1e-5_auto_10x10 | success | 20,660,717,055 | N/A | 20,660,249,775 | 277,174,287,225 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-5_aware_10x10 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,411,665,945 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-5_auto_12x12 | success | 20,660,522,355 | N/A | 20,660,249,775 | 282,139,205,370 | N/A | 4,632,944,910 | 4,393,035,570 | 140 | 63,000 | 15 |
| p1e-5_aware_12x12 | success | 20,660,502,885 | N/A | 20,660,249,775 | 263,310,391,410 | N/A | 4,632,944,910 | 4,393,035,570 | 140 | 63,000 | 15 |
| p1e-2_auto_8x8 | success | 3,527,107,320 | N/A | 3,527,097,585 | 51,444,091,545 | N/A | 184,361,430 | 168,259,740 | 60 | 20,280 | 13 |
| p1e-2_aware_8x8 | success | 3,527,107,320 | N/A | 3,527,097,585 | 51,085,327,590 | N/A | 184,361,430 | 168,259,740 | 60 | 20,280 | 13 |
| p1e-2_auto_10x10 | success | 3,527,107,320 | N/A | 3,527,097,585 | 53,782,623,510 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |
| p1e-2_aware_10x10 | success | 3,527,107,320 | N/A | 3,527,097,585 | 50,703,199,635 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |
| p1e-2_auto_12x12 | success | 3,527,107,320 | N/A | 3,527,097,585 | 55,087,162,185 | N/A | 184,361,430 | 168,259,740 | 140 | 47,320 | 13 |
| p1e-2_aware_12x12 | success | 3,527,107,320 | N/A | 3,527,097,585 | 51,080,693,730 | N/A | 184,361,430 | 168,259,740 | 140 | 47,320 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | success | 15 | 10,000 | 2,122,298 | N/A | 2,122,265 | 33 | 27,201,334 | N/A | 60 | 27,000 | 15 | 475,906 | 451,262 |
| p1e-5_aware_8x8 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 27,047,597 | N/A | 60 | 27,000 | 15 | 475,906 | 451,262 |
| p1e-5_auto_10x10 | success | 15 | 10,000 | 2,122,313 | N/A | 2,122,265 | 48 | 28,471,935 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-5_aware_10x10 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,955,487 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-5_auto_12x12 | success | 15 | 10,000 | 2,122,293 | N/A | 2,122,265 | 28 | 28,981,942 | N/A | 140 | 63,000 | 15 | 475,906 | 451,262 |
| p1e-5_aware_12x12 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 27,047,806 | N/A | 140 | 63,000 | 15 | 475,906 | 451,262 |
| p1e-2_auto_8x8 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,284,447 | N/A | 60 | 20,280 | 13 | 18,938 | 17,284 |
| p1e-2_aware_8x8 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,247,594 | N/A | 60 | 20,280 | 13 | 18,938 | 17,284 |
| p1e-2_auto_10x10 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,524,666 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |
| p1e-2_aware_10x10 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,208,341 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |
| p1e-2_auto_12x12 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,658,671 | N/A | 140 | 47,320 | 13 | 18,938 | 17,284 |
| p1e-2_aware_12x12 | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,247,118 | N/A | 140 | 47,320 | 13 | 18,938 | 17,284 |

## H6 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 7.36349e-05 | 4 | 0.00015936 | 11604.6 | 11,605 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | failed | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-5_aware_8x8 | success | 53,107,857,055 | N/A | 53,107,787,425 | 799,057,830,285 | N/A | 11,900,695,400 | 11,214,932,740 | 60 | 27,000 | 15 |
| p1e-5_auto_10x10 | success | 53,108,240,020 | N/A | 53,107,787,425 | 818,978,625,135 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-5_aware_10x10 | success | 53,107,845,450 | N/A | 53,107,787,425 | 786,525,439,920 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-5_auto_12x12 | success | 53,107,880,265 | N/A | 53,107,787,425 | 829,919,749,505 | N/A | 11,900,695,400 | 11,214,932,740 | 140 | 63,000 | 15 |
| p1e-5_aware_12x12 | success | 53,107,787,425 | N/A | 53,107,787,425 | 789,277,519,250 | N/A | 11,900,695,400 | 11,214,932,740 | 140 | 63,000 | 15 |
| p1e-2_auto_8x8 | failed | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-2_aware_8x8 | success | 8,273,552,650 | N/A | 8,275,200,560 | 139,792,588,265 | N/A | 201,114,650 | 177,440,450 | 60 | 27,000 | 15 |
| p1e-2_auto_10x10 | success | 8,273,204,500 | N/A | 8,275,200,560 | 146,077,809,845 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |
| p1e-2_aware_10x10 | success | 8,273,158,080 | N/A | 8,275,200,560 | 139,825,848,195 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |
| p1e-2_auto_12x12 | success | 8,273,158,080 | N/A | 8,275,200,560 | 149,943,783,495 | N/A | 201,114,650 | 177,440,450 | 140 | 63,000 | 15 |
| p1e-2_aware_12x12 | success | 8,273,158,080 | N/A | 8,275,200,560 | 140,667,744,525 | N/A | 201,114,650 | 177,440,450 | 140 | 63,000 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | failed | 15 | 10,000 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1,025,480 | 1,007,321 |
| p1e-5_aware_8x8 | success | 15 | 10,000 | 4,576,291 | N/A | 4,576,285 | 6 | 68,854,617 | N/A | 60 | 27,000 | 15 | 1,025,480 | 966,388 |
| p1e-5_auto_10x10 | success | 15 | 10,000 | 4,576,324 | N/A | 4,576,285 | 39 | 70,571,187 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-5_aware_10x10 | success | 15 | 10,000 | 4,576,290 | N/A | 4,576,285 | 5 | 67,774,704 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-5_auto_12x12 | success | 15 | 10,000 | 4,576,293 | N/A | 4,576,285 | 8 | 71,513,981 | N/A | 140 | 63,000 | 15 | 1,025,480 | 966,388 |
| p1e-5_aware_12x12 | success | 15 | 10,000 | 4,576,285 | N/A | 4,576,285 | 0 | 68,011,850 | N/A | 140 | 63,000 | 15 | 1,025,480 | 966,388 |
| p1e-2_auto_8x8 | failed | 15 | 10,000 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 17,330 | 16,567 |
| p1e-2_aware_8x8 | success | 15 | 10,000 | 712,930 | N/A | 713,072 | -142 | 12,045,893 | N/A | 60 | 27,000 | 15 | 17,330 | 15,290 |
| p1e-2_auto_10x10 | success | 15 | 10,000 | 712,900 | N/A | 713,072 | -172 | 12,587,489 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |
| p1e-2_aware_10x10 | success | 15 | 10,000 | 712,896 | N/A | 713,072 | -176 | 12,048,759 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |
| p1e-2_auto_12x12 | success | 15 | 10,000 | 712,896 | N/A | 713,072 | -176 | 12,920,619 | N/A | 140 | 63,000 | 15 | 17,330 | 15,290 |
| p1e-2_aware_12x12 | success | 15 | 10,000 | 712,896 | N/A | 713,072 | -176 | 12,121,305 | N/A | 140 | 63,000 | 15 | 17,330 | 15,290 |

## H7 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 6.61457e-05 | 4 | 0.00015936 | 11297.6 | 11,298 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | failed | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-5_aware_8x8 | success | 111,379,864,260 | N/A | 100,222,998,876 | 1,921,860,491,586 | N/A | 22,276,334,388 | 21,032,469,780 | 60 | 34,680 | 17 |
| p1e-5_auto_10x10 | success | 100,225,100,304 | N/A | 100,222,998,876 | 1,743,496,536,516 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-5_aware_10x10 | success | 100,232,466,600 | N/A | 100,222,998,876 | 1,684,993,379,790 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-5_auto_12x12 | success | 100,224,953,430 | N/A | 100,222,998,876 | 1,775,973,032,946 | N/A | 22,276,334,388 | 21,032,469,780 | 140 | 80,920 | 17 |
| p1e-5_aware_12x12 | success | 100,224,896,940 | N/A | 100,222,998,876 | 1,700,644,894,620 | N/A | 22,276,334,388 | 21,032,469,780 | 140 | 80,920 | 17 |
| p1e-2_auto_8x8 | failed | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| p1e-2_aware_8x8 | success | 15,688,549,674 | N/A | 15,649,910,514 | 303,460,834,110 | N/A | 260,870,820 | 235,585,896 | 60 | 27,000 | 15 |
| p1e-2_auto_10x10 | success | 15,648,091,536 | N/A | 15,649,910,514 | 312,366,708,570 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |
| p1e-2_aware_10x10 | success | 15,657,638,346 | N/A | 15,649,910,514 | 298,540,792,368 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |
| p1e-2_auto_12x12 | success | 15,648,091,536 | N/A | 15,649,910,514 | 322,220,586,912 | N/A | 260,870,820 | 235,585,896 | 140 | 63,000 | 15 |
| p1e-2_aware_12x12 | success | 15,648,091,536 | N/A | 15,649,910,514 | 299,447,965,278 | N/A | 260,870,820 | 235,585,896 | 140 | 63,000 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_8x8 | failed | 15 | 10,000 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1,971,706 | 1,938,416 |
| p1e-5_aware_8x8 | success | 15 | 10,000 | 9,858,370 | N/A | 8,870,862 | 987,508 | 170,106,257 | N/A | 60 | 34,680 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_auto_10x10 | success | 15 | 10,000 | 8,871,048 | N/A | 8,870,862 | 186 | 154,319,042 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_aware_10x10 | success | 15 | 10,000 | 8,871,700 | N/A | 8,870,862 | 838 | 149,140,855 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_auto_12x12 | success | 15 | 10,000 | 8,871,035 | N/A | 8,870,862 | 173 | 157,193,577 | N/A | 140 | 80,920 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_aware_12x12 | success | 15 | 10,000 | 8,871,030 | N/A | 8,870,862 | 168 | 150,526,190 | N/A | 140 | 80,920 | 17 | 1,971,706 | 1,861,610 |
| p1e-2_auto_8x8 | failed | 15 | 10,000 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 23,090 | 22,109 |
| p1e-2_aware_8x8 | success | 15 | 10,000 | 1,388,613 | N/A | 1,385,193 | 3,420 | 26,859,695 | N/A | 60 | 27,000 | 15 | 23,090 | 20,852 |
| p1e-2_auto_10x10 | success | 15 | 10,000 | 1,385,032 | N/A | 1,385,193 | -161 | 27,647,965 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
| p1e-2_aware_10x10 | success | 15 | 10,000 | 1,385,877 | N/A | 1,385,193 | 684 | 26,424,216 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
| p1e-2_auto_12x12 | success | 15 | 10,000 | 1,385,032 | N/A | 1,385,193 | -161 | 28,520,144 | N/A | 140 | 63,000 | 15 | 23,090 | 20,852 |
| p1e-2_aware_12x12 | success | 15 | 10,000 | 1,385,032 | N/A | 1,385,193 | -161 | 26,504,511 | N/A | 140 | 63,000 | 15 | 23,090 | 20,852 |

## Failed Or Skipped Cases

| molecule | pf | case | status | type | message |
| --- | --- | --- | --- | --- | --- |
| H6 | 4th(new_2) | p1e-5_auto_8x8 | failed | RuntimeError | quration command failed (code=1): /home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H6_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_/2a0d0f00e8c7884d/compile.yaml --verbose<br>2026-07-12 02:48:35 - INFO  - Load IR.<br>2026-07-12 02:48:36 - INFO  - Find function.<br>2026-07-12 02:48:37 - INFO  - Simplify IR before compiling to SC_LS_FIXED_V0.<br>2026-07-12 02:48:37 - INFO  - Lowering IR to the machine function of SC_LS_FIXED_V0.<br>2026-07-12 02:48:39 - INFO  - Run passes.<br>2026-07-12 02:48:39 - INFO  - Run InitCompileInfo<br>2026-07-12 02:48:39 - INFO  - Initialize compile information<br>2026-07-12 02:48:39 - INFO  - Run Mapping<br>2026-07-12 02:48:39 - ERROR - Failed to find partition<br>Failed to find place to map qubits<br>Command exited with non-zero status 1<br>	Command being timed: "/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H6_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_/2a0d0f00e8c7884d/compile.yaml --verbose"<br>	User time (seconds): 3.65<br>	System time (seconds): 0.47<br>	Percent of CPU this job got: 99%<br>	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:04.12<br>	Average shared text size (kbytes): 0<br>	Average unshared data size (kbytes): 0<br>	Average stack size (kbytes): 0<br>	Average total size (kbytes): 0<br>	Maximum resident set size (kbytes): 1653872<br>	Average resident set size (kbytes): 0<br>	Major (requiring I/O) page faults: 0<br>	Minor (reclaiming a frame) page faults: 482440<br>	Voluntary context switches: 1<br>	Involuntary context switches: 23<br>	Swaps: 0<br>	File system inputs: 0<br>	File system outputs: 0<br>	Socket messages sent: 0<br>	Socket messages received: 0<br>	Signals delivered: 0<br>	Page size (bytes): 4096<br>	Exit status: 1 |
| H6 | 4th(new_2) | p1e-2_auto_8x8 | failed | RuntimeError | quration command failed (code=1): /home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H6_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_/c15c7cdac498c0a2/compile.yaml --verbose<br>2026-07-12 02:53:12 - INFO  - Load IR.<br>2026-07-12 02:53:13 - INFO  - Find function.<br>2026-07-12 02:53:13 - INFO  - Simplify IR before compiling to SC_LS_FIXED_V0.<br>2026-07-12 02:53:13 - INFO  - Lowering IR to the machine function of SC_LS_FIXED_V0.<br>2026-07-12 02:53:14 - INFO  - Run passes.<br>2026-07-12 02:53:14 - INFO  - Run InitCompileInfo<br>2026-07-12 02:53:14 - INFO  - Initialize compile information<br>2026-07-12 02:53:14 - INFO  - Run Mapping<br>2026-07-12 02:53:14 - ERROR - Failed to find partition<br>Failed to find place to map qubits<br>Command exited with non-zero status 1<br>	Command being timed: "/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H6_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_/c15c7cdac498c0a2/compile.yaml --verbose"<br>	User time (seconds): 1.02<br>	System time (seconds): 0.12<br>	Percent of CPU this job got: 100%<br>	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.15<br>	Average shared text size (kbytes): 0<br>	Average unshared data size (kbytes): 0<br>	Average stack size (kbytes): 0<br>	Average total size (kbytes): 0<br>	Maximum resident set size (kbytes): 502588<br>	Average resident set size (kbytes): 0<br>	Major (requiring I/O) page faults: 0<br>	Minor (reclaiming a frame) page faults: 132207<br>	Voluntary context switches: 1<br>	Involuntary context switches: 6<br>	Swaps: 0<br>	File system inputs: 0<br>	File system outputs: 0<br>	Socket messages sent: 0<br>	Socket messages received: 0<br>	Signals delivered: 0<br>	Page size (bytes): 4096<br>	Exit status: 1 |
| H7 | 4th(new_2) | p1e-5_auto_8x8 | failed | RuntimeError | quration command failed (code=1): /home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H7_sto-3g_triplet_1__distance_100_charge_1_grouping__4th_new_2_/6f502815a177c029/compile.yaml --verbose<br>2026-07-12 02:54:06 - INFO  - Load IR.<br>2026-07-12 02:54:08 - INFO  - Find function.<br>2026-07-12 02:54:10 - INFO  - Simplify IR before compiling to SC_LS_FIXED_V0.<br>2026-07-12 02:54:11 - INFO  - Lowering IR to the machine function of SC_LS_FIXED_V0.<br>2026-07-12 02:54:13 - INFO  - Run passes.<br>2026-07-12 02:54:14 - INFO  - Run InitCompileInfo<br>2026-07-12 02:54:14 - INFO  - Initialize compile information<br>2026-07-12 02:54:14 - INFO  - Run Mapping<br>2026-07-12 02:54:14 - ERROR - Failed to find partition<br>Failed to find place to map qubits<br>Command exited with non-zero status 1<br>	Command being timed: "/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H7_sto-3g_triplet_1__distance_100_charge_1_grouping__4th_new_2_/6f502815a177c029/compile.yaml --verbose"<br>	User time (seconds): 7.21<br>	System time (seconds): 0.86<br>	Percent of CPU this job got: 99%<br>	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:08.08<br>	Average shared text size (kbytes): 0<br>	Average unshared data size (kbytes): 0<br>	Average stack size (kbytes): 0<br>	Average total size (kbytes): 0<br>	Maximum resident set size (kbytes): 3196624<br>	Average resident set size (kbytes): 0<br>	Major (requiring I/O) page faults: 0<br>	Minor (reclaiming a frame) page faults: 949119<br>	Voluntary context switches: 1<br>	Involuntary context switches: 35<br>	Swaps: 0<br>	File system inputs: 0<br>	File system outputs: 0<br>	Socket messages sent: 0<br>	Socket messages received: 0<br>	Signals delivered: 0<br>	Page size (bytes): 4096<br>	Exit status: 1 |
| H7 | 4th(new_2) | p1e-2_auto_8x8 | failed | RuntimeError | quration command failed (code=1): /home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H7_sto-3g_triplet_1__distance_100_charge_1_grouping__4th_new_2_/d8b61eb1060eb911/compile.yaml --verbose<br>2026-07-12 03:03:12 - INFO  - Load IR.<br>2026-07-12 03:03:12 - INFO  - Find function.<br>2026-07-12 03:03:13 - INFO  - Simplify IR before compiling to SC_LS_FIXED_V0.<br>2026-07-12 03:03:13 - INFO  - Lowering IR to the machine function of SC_LS_FIXED_V0.<br>2026-07-12 03:03:14 - INFO  - Run passes.<br>2026-07-12 03:03:14 - INFO  - Run InitCompileInfo<br>2026-07-12 03:03:14 - INFO  - Initialize compile information<br>2026-07-12 03:03:14 - INFO  - Run Mapping<br>2026-07-12 03:03:14 - ERROR - Failed to find partition<br>Failed to find place to map qubits<br>Command exited with non-zero status 1<br>	Command being timed: "/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret compile --pipeline /home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_cache/gr/ftqc_compile_topology_qec/H7_sto-3g_triplet_1__distance_100_charge_1_grouping__4th_new_2_/d8b61eb1060eb911/compile.yaml --verbose"<br>	User time (seconds): 2.01<br>	System time (seconds): 0.25<br>	Percent of CPU this job got: 100%<br>	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02.27<br>	Average shared text size (kbytes): 0<br>	Average unshared data size (kbytes): 0<br>	Average stack size (kbytes): 0<br>	Average total size (kbytes): 0<br>	Maximum resident set size (kbytes): 961516<br>	Average resident set size (kbytes): 0<br>	Major (requiring I/O) page faults: 0<br>	Minor (reclaiming a frame) page faults: 258970<br>	Voluntary context switches: 1<br>	Involuntary context switches: 17<br>	Swaps: 0<br>	File system inputs: 0<br>	File system outputs: 0<br>	Socket messages sent: 0<br>	Socket messages received: 0<br>	Signals delivered: 0<br>	Page size (bytes): 4096<br>	Exit status: 1 |
