# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 32 | 32 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H4

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,402,238 | 0 (0.00%) | 100,574,405,347 | 0 (0.00%) |
| p1e-5_explicit_compact_numeric | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 96,459,694,266 | 0 (0.00%) |
| p1e-5_explicit_compact_interaction_aware | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 94,366,965,004 | 0 (0.00%) |
| p1e-5_explicit_perimeter_numeric | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,522,501 | 0 (0.00%) | 104,688,854,036 | 0 (0.00%) |
| p1e-2_auto_greedy_soft | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 20,026,227,559 | 0 (0.00%) |
| p1e-2_explicit_compact_numeric | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,701,233,201 | 0 (0.00%) |
| p1e-2_explicit_compact_interaction_aware | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,600,700,530 | 0 (0.00%) | 19,322,634,344 | 0 (0.00%) |
| p1e-2_explicit_perimeter_numeric | 4th(new_2) | success | 10,933 | 128,091,028 | 0 (0.00%) | 111,254,208 | 0 (0.00%) | 1,601,225,314 | 0 (0.00%) | 21,058,423,022 | 0 (0.00%) |

### H5

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,717,055 | 0 (0.00%) | 277,174,287,225 | 0 (0.00%) |
| p1e-5_explicit_compact_numeric | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 265,669,288,995 | 0 (0.00%) |
| p1e-5_explicit_compact_interaction_aware | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,411,665,945 | 0 (0.00%) |
| p1e-5_explicit_perimeter_numeric | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,843,610 | 0 (0.00%) | 284,015,470,860 | 0 (0.00%) |
| p1e-2_auto_greedy_soft | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 53,782,623,510 | 0 (0.00%) |
| p1e-2_explicit_compact_numeric | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 51,636,503,820 | 0 (0.00%) |
| p1e-2_explicit_compact_interaction_aware | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,107,320 | 0 (0.00%) | 50,703,199,635 | 0 (0.00%) |
| p1e-2_explicit_perimeter_numeric | 4th(new_2) | success | 9,735 | 184,361,430 | 0 (0.00%) | 168,259,740 | 0 (0.00%) | 3,527,418,840 | 0 (0.00%) | 54,654,519,315 | 0 (0.00%) |

### H6

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,108,240,020 | 0 (0.00%) | 818,978,625,135 | 0 (0.00%) |
| p1e-5_explicit_compact_numeric | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,799,030 | 0 (0.00%) | 800,077,991,020 | 0 (0.00%) |
| p1e-5_explicit_compact_interaction_aware | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,845,450 | 0 (0.00%) | 786,525,439,920 | 0 (0.00%) |
| p1e-5_explicit_perimeter_numeric | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,108,982,740 | 0 (0.00%) | 837,108,327,495 | 0 (0.00%) |
| p1e-2_auto_greedy_soft | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,204,500 | 0 (0.00%) | 146,077,809,845 | 0 (0.00%) |
| p1e-2_explicit_compact_numeric | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,158,080 | 0 (0.00%) | 142,256,817,175 | 0 (0.00%) |
| p1e-2_explicit_compact_interaction_aware | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,273,158,080 | 0 (0.00%) | 139,825,848,195 | 0 (0.00%) |
| p1e-2_explicit_perimeter_numeric | 4th(new_2) | success | 11,605 | 201,114,650 | 0 (0.00%) | 177,440,450 | 0 (0.00%) | 8,274,295,370 | 0 (0.00%) | 149,735,671,030 | 0 (0.00%) |

### H7

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,100,304 | 0 (0.00%) | 1,743,496,536,516 | 0 (0.00%) |
| p1e-5_explicit_compact_numeric | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,134,198 | 0 (0.00%) | 1,713,235,849,038 | 0 (0.00%) |
| p1e-5_explicit_compact_interaction_aware | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,232,466,600 | 0 (0.00%) | 1,684,993,379,790 | 0 (0.00%) |
| p1e-5_explicit_perimeter_numeric | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,226,636,832 | 0 (0.00%) | 1,775,250,751,806 | 0 (0.00%) |
| p1e-2_auto_greedy_soft | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,648,091,536 | 0 (0.00%) | 312,366,708,570 | 0 (0.00%) |
| p1e-2_explicit_compact_numeric | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,648,091,536 | 0 (0.00%) | 304,167,105,984 | 0 (0.00%) |
| p1e-2_explicit_compact_interaction_aware | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,657,638,346 | 0 (0.00%) | 298,540,792,368 | 0 (0.00%) |
| p1e-2_explicit_perimeter_numeric | 4th(new_2) | success | 11,298 | 260,870,820 | 0 (0.00%) | 235,585,896 | 0 (0.00%) | 15,649,673,256 | 0 (0.00%) | 316,158,961,356 | 0 (0.00%) |

## H4 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 5.79923e-05 | 4 | 0.00015936 | 10932.1 | 10,933 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 8,900,402,238 | N/A | 8,900,369,439 | 100,574,405,347 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-5_explicit_compact_numeric | success | 8,900,380,372 | N/A | 8,900,369,439 | 96,459,694,266 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-5_explicit_compact_interaction_aware | success | 8,900,380,372 | N/A | 8,900,369,439 | 94,366,965,004 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-5_explicit_perimeter_numeric | success | 8,900,522,501 | N/A | 8,900,369,439 | 104,688,854,036 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| p1e-2_auto_greedy_soft | success | 1,600,700,530 | N/A | 1,600,689,597 | 20,026,227,559 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |
| p1e-2_explicit_compact_numeric | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,701,233,201 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |
| p1e-2_explicit_compact_interaction_aware | success | 1,600,700,530 | N/A | 1,600,689,597 | 19,322,634,344 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |
| p1e-2_explicit_perimeter_numeric | success | 1,601,225,314 | N/A | 1,600,689,597 | 21,058,423,022 | N/A | 128,091,028 | 111,254,208 | 96 | 32,448 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 15 | 10,000 | 814,086 | N/A | 814,083 | 3 | 9,199,159 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-5_explicit_compact_numeric | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,822,802 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-5_explicit_compact_interaction_aware | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 8,631,388 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-5_explicit_perimeter_numeric | success | 15 | 10,000 | 814,097 | N/A | 814,083 | 14 | 9,575,492 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| p1e-2_auto_greedy_soft | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,831,723 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |
| p1e-2_explicit_compact_numeric | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,801,997 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |
| p1e-2_explicit_compact_interaction_aware | success | 15 | 10,000 | 146,410 | N/A | 146,409 | 1 | 1,767,368 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |
| p1e-2_explicit_perimeter_numeric | success | 15 | 10,000 | 146,458 | N/A | 146,409 | 49 | 1,926,134 | N/A | 96 | 32,448 | 13 | 11,716 | 10,176 |

## H5 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 3.64607e-05 | 4 | 0.00015936 | 9734.55 | 9,735 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 20,660,717,055 | N/A | 20,660,249,775 | 277,174,287,225 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-5_explicit_compact_numeric | success | 20,660,502,885 | N/A | 20,660,249,775 | 265,669,288,995 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-5_explicit_compact_interaction_aware | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,411,665,945 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-5_explicit_perimeter_numeric | success | 20,660,843,610 | N/A | 20,660,249,775 | 284,015,470,860 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| p1e-2_auto_greedy_soft | success | 3,527,107,320 | N/A | 3,527,097,585 | 53,782,623,510 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |
| p1e-2_explicit_compact_numeric | success | 3,527,107,320 | N/A | 3,527,097,585 | 51,636,503,820 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |
| p1e-2_explicit_compact_interaction_aware | success | 3,527,107,320 | N/A | 3,527,097,585 | 50,703,199,635 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |
| p1e-2_explicit_perimeter_numeric | success | 3,527,418,840 | N/A | 3,527,097,585 | 54,654,519,315 | N/A | 184,361,430 | 168,259,740 | 96 | 32,448 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 15 | 10,000 | 2,122,313 | N/A | 2,122,265 | 48 | 28,471,935 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-5_explicit_compact_numeric | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 27,290,117 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-5_explicit_compact_interaction_aware | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,955,487 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-5_explicit_perimeter_numeric | success | 15 | 10,000 | 2,122,326 | N/A | 2,122,265 | 61 | 29,174,676 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| p1e-2_auto_greedy_soft | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,524,666 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |
| p1e-2_explicit_compact_numeric | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,304,212 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |
| p1e-2_explicit_compact_interaction_aware | success | 15 | 10,000 | 362,312 | N/A | 362,311 | 1 | 5,208,341 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |
| p1e-2_explicit_perimeter_numeric | success | 15 | 10,000 | 362,344 | N/A | 362,311 | 33 | 5,614,229 | N/A | 96 | 32,448 | 13 | 18,938 | 17,284 |

## H6 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 7.36349e-05 | 4 | 0.00015936 | 11604.6 | 11,605 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 53,108,240,020 | N/A | 53,107,787,425 | 818,978,625,135 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-5_explicit_compact_numeric | success | 53,107,799,030 | N/A | 53,107,787,425 | 800,077,991,020 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-5_explicit_compact_interaction_aware | success | 53,107,845,450 | N/A | 53,107,787,425 | 786,525,439,920 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-5_explicit_perimeter_numeric | success | 53,108,982,740 | N/A | 53,107,787,425 | 837,108,327,495 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| p1e-2_auto_greedy_soft | success | 8,273,204,500 | N/A | 8,275,200,560 | 146,077,809,845 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |
| p1e-2_explicit_compact_numeric | success | 8,273,158,080 | N/A | 8,275,200,560 | 142,256,817,175 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |
| p1e-2_explicit_compact_interaction_aware | success | 8,273,158,080 | N/A | 8,275,200,560 | 139,825,848,195 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |
| p1e-2_explicit_perimeter_numeric | success | 8,274,295,370 | N/A | 8,275,200,560 | 149,735,671,030 | N/A | 201,114,650 | 177,440,450 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 15 | 10,000 | 4,576,324 | N/A | 4,576,285 | 39 | 70,571,187 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-5_explicit_compact_numeric | success | 15 | 10,000 | 4,576,286 | N/A | 4,576,285 | 1 | 68,942,524 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-5_explicit_compact_interaction_aware | success | 15 | 10,000 | 4,576,290 | N/A | 4,576,285 | 5 | 67,774,704 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-5_explicit_perimeter_numeric | success | 15 | 10,000 | 4,576,388 | N/A | 4,576,285 | 103 | 72,133,419 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| p1e-2_auto_greedy_soft | success | 15 | 10,000 | 712,900 | N/A | 713,072 | -172 | 12,587,489 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |
| p1e-2_explicit_compact_numeric | success | 15 | 10,000 | 712,896 | N/A | 713,072 | -176 | 12,258,235 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |
| p1e-2_explicit_compact_interaction_aware | success | 15 | 10,000 | 712,896 | N/A | 713,072 | -176 | 12,048,759 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |
| p1e-2_explicit_perimeter_numeric | success | 15 | 10,000 | 712,994 | N/A | 713,072 | -78 | 12,902,686 | N/A | 96 | 43,200 | 15 | 17,330 | 15,290 |

## H7 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 6.61457e-05 | 4 | 0.00015936 | 11297.6 | 11,298 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 100,225,100,304 | N/A | 100,222,998,876 | 1,743,496,536,516 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-5_explicit_compact_numeric | success | 100,225,134,198 | N/A | 100,222,998,876 | 1,713,235,849,038 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-5_explicit_compact_interaction_aware | success | 100,232,466,600 | N/A | 100,222,998,876 | 1,684,993,379,790 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-5_explicit_perimeter_numeric | success | 100,226,636,832 | N/A | 100,222,998,876 | 1,775,250,751,806 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| p1e-2_auto_greedy_soft | success | 15,648,091,536 | N/A | 15,649,910,514 | 312,366,708,570 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |
| p1e-2_explicit_compact_numeric | success | 15,648,091,536 | N/A | 15,649,910,514 | 304,167,105,984 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |
| p1e-2_explicit_compact_interaction_aware | success | 15,657,638,346 | N/A | 15,649,910,514 | 298,540,792,368 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |
| p1e-2_explicit_perimeter_numeric | success | 15,649,673,256 | N/A | 15,649,910,514 | 316,158,961,356 | N/A | 260,870,820 | 235,585,896 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p1e-5_auto_greedy_soft | success | 15 | 10,000 | 8,871,048 | N/A | 8,870,862 | 186 | 154,319,042 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_explicit_compact_numeric | success | 15 | 10,000 | 8,871,051 | N/A | 8,870,862 | 189 | 151,640,631 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_explicit_compact_interaction_aware | success | 15 | 10,000 | 8,871,700 | N/A | 8,870,862 | 838 | 149,140,855 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-5_explicit_perimeter_numeric | success | 15 | 10,000 | 8,871,184 | N/A | 8,870,862 | 322 | 157,129,647 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| p1e-2_auto_greedy_soft | success | 15 | 10,000 | 1,385,032 | N/A | 1,385,193 | -161 | 27,647,965 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
| p1e-2_explicit_compact_numeric | success | 15 | 10,000 | 1,385,032 | N/A | 1,385,193 | -161 | 26,922,208 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
| p1e-2_explicit_compact_interaction_aware | success | 15 | 10,000 | 1,385,877 | N/A | 1,385,193 | 684 | 26,424,216 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
| p1e-2_explicit_perimeter_numeric | success | 15 | 10,000 | 1,385,172 | N/A | 1,385,193 | -21 | 27,983,622 | N/A | 96 | 43,200 | 15 | 23,090 | 20,852 |
