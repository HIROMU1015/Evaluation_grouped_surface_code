# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 4 | 4 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H6

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,764,215 | 0 (0.00%) | 802,737,868,625 | 0 (0.00%) |
| m0_center | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,764,215 | 0 (0.00%) | 802,737,868,625 | 0 (0.00%) |
| m0_right | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,764,215 | 0 (0.00%) | 802,737,868,625 | 0 (0.00%) |
| m0_far_corner | 4th(new_2) | success | 11,605 | 11,900,695,400 | 0 (0.00%) | 11,214,932,740 | 0 (0.00%) | 53,107,764,215 | 0 (0.00%) | 802,780,575,025 | 0 (0.00%) |

## H6 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 7.36349e-05 | 4 | 0.00015936 | 11604.6 | 11,605 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | success | 53,107,764,215 | N/A | 53,107,787,425 | 802,737,868,625 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| m0_center | success | 53,107,764,215 | N/A | 53,107,787,425 | 802,737,868,625 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| m0_right | success | 53,107,764,215 | N/A | 53,107,787,425 | 802,737,868,625 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |
| m0_far_corner | success | 53,107,764,215 | N/A | 53,107,787,425 | 802,780,575,025 | N/A | 11,900,695,400 | 11,214,932,740 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m0_left | success | 15 | 10,000 | 4,576,283 | N/A | 4,576,285 | -2 | 69,171,725 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| m0_center | success | 15 | 10,000 | 4,576,283 | N/A | 4,576,285 | -2 | 69,171,725 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| m0_right | success | 15 | 10,000 | 4,576,283 | N/A | 4,576,285 | -2 | 69,171,725 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
| m0_far_corner | success | 15 | 10,000 | 4,576,283 | N/A | 4,576,285 | -2 | 69,175,405 | N/A | 96 | 43,200 | 15 | 1,025,480 | 966,388 |
