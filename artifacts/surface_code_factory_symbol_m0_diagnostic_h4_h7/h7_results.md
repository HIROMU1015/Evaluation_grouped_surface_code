# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 4 | 4 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H7

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,732,992 | 0 (0.00%) | 1,731,886,598,736 | 0 (0.00%) |
| m0_center | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,721,694 | 0 (0.00%) | 1,731,918,289,626 | 0 (0.00%) |
| m0_right | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,732,992 | 0 (0.00%) | 1,731,886,598,736 | 0 (0.00%) |
| m0_far_corner | 4th(new_2) | success | 11,298 | 22,276,334,388 | 0 (0.00%) | 21,032,469,780 | 0 (0.00%) | 100,225,834,674 | 0 (0.00%) | 1,733,635,337,070 | 0 (0.00%) |

## H7 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 6.61457e-05 | 4 | 0.00015936 | 11297.6 | 11,298 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | success | 100,225,732,992 | N/A | 100,222,998,876 | 1,731,886,598,736 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| m0_center | success | 100,225,721,694 | N/A | 100,222,998,876 | 1,731,918,289,626 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| m0_right | success | 100,225,732,992 | N/A | 100,222,998,876 | 1,731,886,598,736 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |
| m0_far_corner | success | 100,225,834,674 | N/A | 100,222,998,876 | 1,733,635,337,070 | N/A | 22,276,334,388 | 21,032,469,780 | 96 | 55,488 | 17 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | success | 15 | 10,000 | 8,871,104 | N/A | 8,870,862 | 242 | 153,291,432 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| m0_center | success | 15 | 10,000 | 8,871,103 | N/A | 8,870,862 | 241 | 153,294,237 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| m0_right | success | 15 | 10,000 | 8,871,104 | N/A | 8,870,862 | 242 | 153,291,432 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
| m0_far_corner | success | 15 | 10,000 | 8,871,113 | N/A | 8,870,862 | 251 | 153,446,215 | N/A | 96 | 55,488 | 17 | 1,971,706 | 1,861,610 |
