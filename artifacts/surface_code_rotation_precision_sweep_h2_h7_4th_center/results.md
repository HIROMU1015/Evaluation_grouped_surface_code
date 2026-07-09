# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 30 | 30 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H2

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 7,416 | 59,936,112 | 0 (0.00%) | 48,693,456 | 0 (0.00%) | 226,188,000 | 0 (0.00%) | 1,696,580,568 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 7,416 | 53,202,384 | 0 (0.00%) | 43,353,936 | 0 (0.00%) | 200,877,192 | 0 (0.00%) | 1,510,683,696 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 7,416 | 47,284,416 | 0 (0.00%) | 38,444,544 | 0 (0.00%) | 178,199,064 | 0 (0.00%) | 1,348,169,472 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 7,416 | 41,781,744 | 0 (0.00%) | 34,128,432 | 0 (0.00%) | 160,259,760 | 0 (0.00%) | 1,213,828,632 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 7,416 | 33,149,520 | 0 (0.00%) | 26,979,408 | 0 (0.00%) | 126,976,752 | 0 (0.00%) | 973,127,520 | 0 (0.00%) |

### H3

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 8,175 | 413,115,450 | 0 (0.00%) | 389,130,000 | 0 (0.00%) | 1,807,590,600 | 0 (0.00%) | 16,849,091,925 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 8,175 | 373,940,850 | 0 (0.00%) | 352,375,200 | 0 (0.00%) | 1,650,802,275 | 0 (0.00%) | 15,408,370,800 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 8,175 | 328,422,450 | 0 (0.00%) | 309,178,500 | 0 (0.00%) | 1,487,343,150 | 0 (0.00%) | 13,882,572,450 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 8,175 | 287,400,300 | 0 (0.00%) | 270,952,200 | 0 (0.00%) | 1,334,233,575 | 0 (0.00%) | 12,464,013,750 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 8,175 | 236,813,400 | 0 (0.00%) | 222,981,300 | 0 (0.00%) | 1,148,374,950 | 0 (0.00%) | 10,753,223,325 | 0 (0.00%) |

### H4

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,402,238 | 0 (0.00%) | 100,574,405,347 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 10,933 | 1,786,299,138 | 0 (0.00%) | 1,680,555,162 | 0 (0.00%) | 8,035,984,593 | 0 (0.00%) | 90,939,141,514 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 10,933 | 1,602,712,202 | 0 (0.00%) | 1,508,863,330 | 0 (0.00%) | 7,327,209,136 | 0 (0.00%) | 83,093,631,647 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 10,933 | 1,361,136,634 | 0 (0.00%) | 1,278,833,010 | 0 (0.00%) | 6,345,863,056 | 0 (0.00%) | 72,255,344,226 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 10,933 | 1,112,957,534 | 0 (0.00%) | 1,043,839,108 | 0 (0.00%) | 5,456,419,774 | 0 (0.00%) | 62,342,917,910 | 0 (0.00%) |

### H5

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,717,055 | 0 (0.00%) | 277,174,287,225 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 9,735 | 4,186,322,580 | 0 (0.00%) | 3,968,706,390 | 0 (0.00%) | 19,031,574,540 | 0 (0.00%) | 255,744,495,435 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 9,735 | 3,646,049,550 | 0 (0.00%) | 3,455,107,260 | 0 (0.00%) | 16,987,789,170 | 0 (0.00%) | 229,108,873,455 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 9,735 | 3,103,440,120 | 0 (0.00%) | 2,951,282,070 | 0 (0.00%) | 14,903,720,370 | 0 (0.00%) | 201,863,197,965 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 9,735 | 2,427,500,130 | 0 (0.00%) | 2,307,584,400 | 0 (0.00%) | 12,309,333,135 | 0 (0.00%) | 167,788,682,820 | 0 (0.00%) |

### H6

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,108,240,020 | 0 (0.00%) | 818,978,625,135 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 11,605 | 10,674,812,830 | 0 (0.00%) | 10,070,099,490 | 0 (0.00%) | 48,770,708,800 | 0 (0.00%) | 752,743,110,845 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 11,605 | 9,353,374,690 | 0 (0.00%) | 8,826,623,740 | 0 (0.00%) | 43,591,641,005 | 0 (0.00%) | 675,089,193,350 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 11,605 | 8,010,652,980 | 0 (0.00%) | 7,561,052,070 | 0 (0.00%) | 38,523,192,070 | 0 (0.00%) | 598,764,709,840 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 11,605 | 5,847,666,660 | 0 (0.00%) | 5,542,153,430 | 0 (0.00%) | 30,309,764,925 | 0 (0.00%) | 475,688,659,875 | 0 (0.00%) |

### H7

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,100,304 | 0 (0.00%) | 1,743,496,536,516 | 0 (0.00%) |
| rot_prec_3e-5 | 4th(new_2) | success | 11,298 | 20,019,671,868 | 0 (0.00%) | 18,920,060,124 | 0 (0.00%) | 91,728,111,762 | 0 (0.00%) | 1,598,430,555,456 | 0 (0.00%) |
| rot_prec_1e-4 | 4th(new_2) | success | 11,298 | 17,608,723,860 | 0 (0.00%) | 16,636,440,576 | 0 (0.00%) | 82,525,630,908 | 0 (0.00%) | 1,442,568,533,238 | 0 (0.00%) |
| rot_prec_3e-4 | 4th(new_2) | success | 11,298 | 14,762,712,468 | 0 (0.00%) | 14,032,161,192 | 0 (0.00%) | 71,811,161,310 | 0 (0.00%) | 1,260,699,870,780 | 0 (0.00%) |
| rot_prec_1e-3 | 4th(new_2) | success | 11,298 | 9,689,481,144 | 0 (0.00%) | 9,205,497,420 | 0 (0.00%) | 52,321,727,178 | 0 (0.00%) | 931,195,768,314 | 0 (0.00%) |

## H2 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 1.22791e-05 | 4 | 0.00015936 | 7415.68 | 7,416 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 226,188,000 | N/A | 226,180,584 | 1,696,580,568 | N/A | 59,936,112 | 48,693,456 | 96 | 23,232 | 11 |
| rot_prec_3e-5 | success | 200,877,192 | N/A | 200,869,776 | 1,510,683,696 | N/A | 53,202,384 | 43,353,936 | 96 | 23,232 | 11 |
| rot_prec_1e-4 | success | 178,199,064 | N/A | 178,191,648 | 1,348,169,472 | N/A | 47,284,416 | 38,444,544 | 96 | 23,232 | 11 |
| rot_prec_3e-4 | success | 160,259,760 | N/A | 160,252,344 | 1,213,828,632 | N/A | 41,781,744 | 34,128,432 | 96 | 23,232 | 11 |
| rot_prec_1e-3 | success | 126,976,752 | N/A | 126,969,336 | 973,127,520 | N/A | 33,149,520 | 26,979,408 | 96 | 23,232 | 11 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 30,500 | N/A | 30,499 | 1 | 228,773 | N/A | 96 | 23,232 | 11 | 8,082 | 6,566 |
| rot_prec_3e-5 | success | 15 | 10,000 | 27,087 | N/A | 27,086 | 1 | 203,706 | N/A | 96 | 23,232 | 11 | 7,174 | 5,846 |
| rot_prec_1e-4 | success | 15 | 10,000 | 24,029 | N/A | 24,028 | 1 | 181,792 | N/A | 96 | 23,232 | 11 | 6,376 | 5,184 |
| rot_prec_3e-4 | success | 15 | 10,000 | 21,610 | N/A | 21,609 | 1 | 163,677 | N/A | 96 | 23,232 | 11 | 5,634 | 4,602 |
| rot_prec_1e-3 | success | 15 | 10,000 | 17,122 | N/A | 17,121 | 1 | 131,220 | N/A | 96 | 23,232 | 11 | 4,470 | 3,638 |

## H3 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 1.81264e-05 | 4 | 0.00015936 | 8174.06 | 8,175 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 1,807,590,600 | N/A | 1,807,582,425 | 16,849,091,925 | N/A | 413,115,450 | 389,130,000 | 96 | 32,448 | 13 |
| rot_prec_3e-5 | success | 1,650,802,275 | N/A | 1,650,794,100 | 15,408,370,800 | N/A | 373,940,850 | 352,375,200 | 96 | 32,448 | 13 |
| rot_prec_1e-4 | success | 1,487,343,150 | N/A | 1,487,334,975 | 13,882,572,450 | N/A | 328,422,450 | 309,178,500 | 96 | 32,448 | 13 |
| rot_prec_3e-4 | success | 1,334,233,575 | N/A | 1,334,225,400 | 12,464,013,750 | N/A | 287,400,300 | 270,952,200 | 96 | 32,448 | 13 |
| rot_prec_1e-3 | success | 1,148,374,950 | N/A | 1,148,366,775 | 10,753,223,325 | N/A | 236,813,400 | 222,981,300 | 96 | 32,448 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 221,112 | N/A | 221,111 | 1 | 2,061,051 | N/A | 96 | 32,448 | 13 | 50,534 | 47,600 |
| rot_prec_3e-5 | success | 15 | 10,000 | 201,933 | N/A | 201,932 | 1 | 1,884,816 | N/A | 96 | 32,448 | 13 | 45,742 | 43,104 |
| rot_prec_1e-4 | success | 15 | 10,000 | 181,938 | N/A | 181,937 | 1 | 1,698,174 | N/A | 96 | 32,448 | 13 | 40,174 | 37,820 |
| rot_prec_3e-4 | success | 15 | 10,000 | 163,209 | N/A | 163,208 | 1 | 1,524,650 | N/A | 96 | 32,448 | 13 | 35,156 | 33,144 |
| rot_prec_1e-3 | success | 15 | 10,000 | 140,474 | N/A | 140,473 | 1 | 1,315,379 | N/A | 96 | 32,448 | 13 | 28,968 | 27,276 |

## H4 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 5.79923e-05 | 4 | 0.00015936 | 10932.1 | 10,933 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 8,900,402,238 | N/A | 8,900,369,439 | 100,574,405,347 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| rot_prec_3e-5 | success | 8,035,984,593 | N/A | 8,035,908,062 | 90,939,141,514 | N/A | 1,786,299,138 | 1,680,555,162 | 96 | 32,448 | 13 |
| rot_prec_1e-4 | success | 7,327,209,136 | N/A | 7,327,198,203 | 83,093,631,647 | N/A | 1,602,712,202 | 1,508,863,330 | 96 | 32,448 | 13 |
| rot_prec_3e-4 | success | 6,345,863,056 | N/A | 6,345,852,123 | 72,255,344,226 | N/A | 1,361,136,634 | 1,278,833,010 | 96 | 32,448 | 13 |
| rot_prec_1e-3 | success | 5,456,419,774 | N/A | 5,456,518,171 | 62,342,917,910 | N/A | 1,112,957,534 | 1,043,839,108 | 96 | 32,448 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 814,086 | N/A | 814,083 | 3 | 9,199,159 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| rot_prec_3e-5 | success | 15 | 10,000 | 735,021 | N/A | 735,014 | 7 | 8,317,858 | N/A | 96 | 32,448 | 13 | 163,386 | 153,714 |
| rot_prec_1e-4 | success | 15 | 10,000 | 670,192 | N/A | 670,191 | 1 | 7,600,259 | N/A | 96 | 32,448 | 13 | 146,594 | 138,010 |
| rot_prec_3e-4 | success | 15 | 10,000 | 580,432 | N/A | 580,431 | 1 | 6,608,922 | N/A | 96 | 32,448 | 13 | 124,498 | 116,970 |
| rot_prec_1e-3 | success | 15 | 10,000 | 499,078 | N/A | 499,087 | -9 | 5,702,270 | N/A | 96 | 32,448 | 13 | 101,798 | 95,476 |

## H5 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 3.64607e-05 | 4 | 0.00015936 | 9734.55 | 9,735 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 20,660,717,055 | N/A | 20,660,249,775 | 277,174,287,225 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| rot_prec_3e-5 | success | 19,031,574,540 | N/A | 19,031,068,320 | 255,744,495,435 | N/A | 4,186,322,580 | 3,968,706,390 | 96 | 43,200 | 15 |
| rot_prec_1e-4 | success | 16,987,789,170 | N/A | 16,987,380,300 | 229,108,873,455 | N/A | 3,646,049,550 | 3,455,107,260 | 96 | 43,200 | 15 |
| rot_prec_3e-4 | success | 14,903,720,370 | N/A | 14,904,100,035 | 201,863,197,965 | N/A | 3,103,440,120 | 2,951,282,070 | 96 | 43,200 | 15 |
| rot_prec_1e-3 | success | 12,309,333,135 | N/A | 12,309,498,630 | 167,788,682,820 | N/A | 2,427,500,130 | 2,307,584,400 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 2,122,313 | N/A | 2,122,265 | 48 | 28,471,935 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| rot_prec_3e-5 | success | 15 | 10,000 | 1,954,964 | N/A | 1,954,912 | 52 | 26,270,621 | N/A | 96 | 43,200 | 15 | 430,028 | 407,674 |
| rot_prec_1e-4 | success | 15 | 10,000 | 1,745,022 | N/A | 1,744,980 | 42 | 23,534,553 | N/A | 96 | 43,200 | 15 | 374,530 | 354,916 |
| rot_prec_3e-4 | success | 15 | 10,000 | 1,530,942 | N/A | 1,530,981 | -39 | 20,735,819 | N/A | 96 | 43,200 | 15 | 318,792 | 303,162 |
| rot_prec_1e-3 | success | 15 | 10,000 | 1,264,441 | N/A | 1,264,458 | -17 | 17,235,612 | N/A | 96 | 43,200 | 15 | 249,358 | 237,040 |

## H6 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 7.36349e-05 | 4 | 0.00015936 | 11604.6 | 11,605 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 53,108,240,020 | N/A | 53,107,787,425 | 818,978,625,135 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| rot_prec_3e-5 | success | 48,770,708,800 | N/A | 48,770,267,810 | 752,743,110,845 | N/A | 10,674,812,830 | 10,070,099,490 | 96 | 43,200 | 15 |
| rot_prec_1e-4 | success | 43,591,641,005 | N/A | 43,591,153,595 | 675,089,193,350 | N/A | 9,353,374,690 | 8,826,623,740 | 96 | 43,200 | 15 |
| rot_prec_3e-4 | success | 38,523,192,070 | N/A | 38,522,971,575 | 598,764,709,840 | N/A | 8,010,652,980 | 7,561,052,070 | 96 | 43,200 | 15 |
| rot_prec_1e-3 | success | 30,309,764,925 | N/A | 30,309,416,775 | 475,688,659,875 | N/A | 5,847,666,660 | 5,542,153,430 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 4,576,324 | N/A | 4,576,285 | 39 | 70,571,187 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| rot_prec_3e-5 | success | 15 | 10,000 | 4,202,560 | N/A | 4,202,522 | 38 | 64,863,689 | N/A | 96 | 43,200 | 15 | 919,846 | 867,738 |
| rot_prec_1e-4 | success | 15 | 10,000 | 3,756,281 | N/A | 3,756,239 | 42 | 58,172,270 | N/A | 96 | 43,200 | 15 | 805,978 | 760,588 |
| rot_prec_3e-4 | success | 15 | 10,000 | 3,319,534 | N/A | 3,319,515 | 19 | 51,595,408 | N/A | 96 | 43,200 | 15 | 690,276 | 651,534 |
| rot_prec_1e-3 | success | 15 | 10,000 | 2,611,785 | N/A | 2,611,755 | 30 | 40,989,975 | N/A | 96 | 43,200 | 15 | 503,892 | 477,566 |

## H7 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 6.61457e-05 | 4 | 0.00015936 | 11297.6 | 11,298 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 100,225,100,304 | N/A | 100,222,998,876 | 1,743,496,536,516 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| rot_prec_3e-5 | success | 91,728,111,762 | N/A | 91,726,733,406 | 1,598,430,555,456 | N/A | 20,019,671,868 | 18,920,060,124 | 96 | 55,488 | 17 |
| rot_prec_1e-4 | success | 82,525,630,908 | N/A | 82,524,410,724 | 1,442,568,533,238 | N/A | 17,608,723,860 | 16,636,440,576 | 96 | 55,488 | 17 |
| rot_prec_3e-4 | success | 71,811,161,310 | N/A | 71,810,777,178 | 1,260,699,870,780 | N/A | 14,762,712,468 | 14,032,161,192 | 96 | 55,488 | 17 |
| rot_prec_1e-3 | success | 52,321,727,178 | N/A | 52,321,422,132 | 931,195,768,314 | N/A | 9,689,481,144 | 9,205,497,420 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rot_prec_1e-5_baseline | success | 15 | 10,000 | 8,871,048 | N/A | 8,870,862 | 186 | 154,319,042 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| rot_prec_3e-5 | success | 15 | 10,000 | 8,118,969 | N/A | 8,118,847 | 122 | 141,479,072 | N/A | 96 | 55,488 | 17 | 1,771,966 | 1,674,638 |
| rot_prec_1e-4 | success | 15 | 10,000 | 7,304,446 | N/A | 7,304,338 | 108 | 127,683,531 | N/A | 96 | 55,488 | 17 | 1,558,570 | 1,472,512 |
| rot_prec_3e-4 | success | 15 | 10,000 | 6,356,095 | N/A | 6,356,061 | 34 | 111,586,110 | N/A | 96 | 55,488 | 17 | 1,306,666 | 1,242,004 |
| rot_prec_1e-3 | success | 15 | 10,000 | 4,631,061 | N/A | 4,631,034 | 27 | 82,421,293 | N/A | 96 | 43,200 | 15 | 857,628 | 814,790 |
