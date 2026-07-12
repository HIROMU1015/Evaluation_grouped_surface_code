# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 14 | 14 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H5

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 263,308,356,795 | 0 (0.00%) |
| fixed_circuit_aware_8x10 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,630,703,445 | 0 (0.00%) |
| fixed_circuit_aware_9x9 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,663,725,170 | 0 (0.00%) | 264,485,736,900 | 0 (0.00%) |
| fixed_circuit_aware_10x8 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,311,083,925 | 0 (0.00%) |
| fixed_circuit_aware_10x10 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,411,665,945 | 0 (0.00%) |
| fixed_circuit_aware_10x12 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,308,289,980 | 0 (0.00%) |
| fixed_circuit_aware_12x10 | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,502,885 | 0 (0.00%) | 262,625,018,205 | 0 (0.00%) |

### H7

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 111,379,864,260 | 0 (0.00%) | 1,921,860,491,586 | 0 (0.00%) |
| fixed_circuit_aware_8x10 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,231,687,038 | 0 (0.00%) | 1,681,109,748,780 | 0 (0.00%) |
| fixed_circuit_aware_9x9 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,231,867,806 | 0 (0.00%) | 1,705,542,227,382 | 0 (0.00%) |
| fixed_circuit_aware_10x8 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,231,494,972 | 0 (0.00%) | 1,680,689,406,690 | 0 (0.00%) |
| fixed_circuit_aware_10x10 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,232,466,600 | 0 (0.00%) | 1,684,993,379,790 | 0 (0.00%) |
| fixed_circuit_aware_10x12 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,226,444,766 | 0 (0.00%) | 1,696,205,661,864 | 0 (0.00%) |
| fixed_circuit_aware_12x10 | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,226,636,832 | 0 (0.00%) | 1,697,880,364,404 | 0 (0.00%) |

## H5 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 3.64607e-05 | 4 | 0.00015936 | 9734.55 | 9,735 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | success | 20,660,502,885 | N/A | 20,660,249,775 | 263,308,356,795 | N/A | 4,632,944,910 | 4,393,035,570 | 60 | 27,000 | 15 |
| fixed_circuit_aware_8x10 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,630,703,445 | N/A | 4,632,944,910 | 4,393,035,570 | 76 | 34,200 | 15 |
| fixed_circuit_aware_9x9 | success | 20,663,725,170 | N/A | 20,660,249,775 | 264,485,736,900 | N/A | 4,632,944,910 | 4,393,035,570 | 77 | 34,650 | 15 |
| fixed_circuit_aware_10x8 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,311,083,925 | N/A | 4,632,944,910 | 4,393,035,570 | 76 | 34,200 | 15 |
| fixed_circuit_aware_10x10 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,411,665,945 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| fixed_circuit_aware_10x12 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,308,289,980 | N/A | 4,632,944,910 | 4,393,035,570 | 116 | 52,200 | 15 |
| fixed_circuit_aware_12x10 | success | 20,660,502,885 | N/A | 20,660,249,775 | 262,625,018,205 | N/A | 4,632,944,910 | 4,393,035,570 | 116 | 52,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 27,047,597 | N/A | 60 | 27,000 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_8x10 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,977,987 | N/A | 76 | 34,200 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_9x9 | success | 15 | 10,000 | 2,122,622 | N/A | 2,122,265 | 357 | 27,168,540 | N/A | 77 | 34,650 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_10x8 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,945,155 | N/A | 76 | 34,200 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_10x10 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,955,487 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_10x12 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,944,868 | N/A | 116 | 52,200 | 15 | 475,906 | 451,262 |
| fixed_circuit_aware_12x10 | success | 15 | 10,000 | 2,122,291 | N/A | 2,122,265 | 26 | 26,977,403 | N/A | 116 | 52,200 | 15 | 475,906 | 451,262 |

## H7 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 6.61457e-05 | 4 | 0.00015936 | 11297.6 | 11,298 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | success | 111,379,864,260 | N/A | 100,222,998,876 | 1,921,860,491,586 | N/A | 22,276,334,388 | 21,032,469,780 | 60 | 34,680 | 17 |
| fixed_circuit_aware_8x10 | success | 100,231,687,038 | N/A | 100,222,998,876 | 1,681,109,748,780 | N/A | 22,276,334,388 | 21,032,469,780 | 76 | 43,928 | 17 |
| fixed_circuit_aware_9x9 | success | 100,231,867,806 | N/A | 100,222,998,876 | 1,705,542,227,382 | N/A | 22,276,334,388 | 21,032,469,780 | 77 | 44,506 | 17 |
| fixed_circuit_aware_10x8 | success | 100,231,494,972 | N/A | 100,222,998,876 | 1,680,689,406,690 | N/A | 22,276,334,388 | 21,032,469,780 | 76 | 43,928 | 17 |
| fixed_circuit_aware_10x10 | success | 100,232,466,600 | N/A | 100,222,998,876 | 1,684,993,379,790 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| fixed_circuit_aware_10x12 | success | 100,226,444,766 | N/A | 100,222,998,876 | 1,696,205,661,864 | N/A | 22,276,334,388 | 21,032,469,780 | 116 | 67,048 | 17 |
| fixed_circuit_aware_12x10 | success | 100,226,636,832 | N/A | 100,222,998,876 | 1,697,880,364,404 | N/A | 22,276,334,388 | 21,032,469,780 | 116 | 67,048 | 17 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_circuit_aware_8x8 | success | 15 | 10,000 | 9,858,370 | N/A | 8,870,862 | 987,508 | 170,106,257 | N/A | 60 | 34,680 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_8x10 | success | 15 | 10,000 | 8,871,631 | N/A | 8,870,862 | 769 | 148,797,110 | N/A | 76 | 43,928 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_9x9 | success | 15 | 10,000 | 8,871,647 | N/A | 8,870,862 | 785 | 150,959,659 | N/A | 77 | 44,506 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_10x8 | success | 15 | 10,000 | 8,871,614 | N/A | 8,870,862 | 752 | 148,759,905 | N/A | 76 | 43,928 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_10x10 | success | 15 | 10,000 | 8,871,700 | N/A | 8,870,862 | 838 | 149,140,855 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_10x12 | success | 15 | 10,000 | 8,871,167 | N/A | 8,870,862 | 305 | 150,133,268 | N/A | 116 | 67,048 | 17 | 1,971,706 | 1,861,610 |
| fixed_circuit_aware_12x10 | success | 15 | 10,000 | 8,871,184 | N/A | 8,870,862 | 322 | 150,281,498 | N/A | 116 | 67,048 | 17 | 1,971,706 | 1,861,610 |
