# Surface-Code Architecture Sweep

## Summary

| rows | success | failed | skipped |
| --- | --- | --- | --- |
| 8 | 8 | 0 | 0 |

## PF-Step Linear Scaling Comparison

These totals are linear extrapolations from one compiled PF step. For efficient controlled rows, only the Pauli rotations' central RZ gates are controlled. These are not compiled full QPE circuits with phase-register ancilla, inverse QFT, measurements, or repeated QPE iterations.

### H4

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 101,280,458,487 | 0 (0.00%) |
| four_factory_m0_center | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 101,280,371,023 | 0 (0.00%) |
| four_factory_m0_right | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 101,280,458,487 | 0 (0.00%) |
| four_factory_m0_far_corner | 4th(new_2) | success | 10,933 | 2,018,231,800 | 0 (0.00%) | 1,899,586,884 | 0 (0.00%) | 8,900,380,372 | 0 (0.00%) | 101,287,827,329 | 0 (0.00%) |

### H5

| case | PF | status | actions | total magic count | vs 2nd | total magic depth | vs 2nd | total runtime topo | vs 2nd | total qubit volume | vs 2nd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,541,825 | 0 (0.00%) | 274,330,664,520 | 0 (0.00%) |
| four_factory_m0_center | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,541,825 | 0 (0.00%) | 274,330,664,520 | 0 (0.00%) |
| four_factory_m0_right | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,541,825 | 0 (0.00%) | 274,330,664,520 | 0 (0.00%) |
| four_factory_m0_far_corner | 4th(new_2) | success | 9,735 | 4,632,944,910 | 0 (0.00%) | 4,393,035,570 | 0 (0.00%) | 20,660,541,825 | 0 (0.00%) | 274,460,840,940 | 0 (0.00%) |

## H4 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 5.79923e-05 | 4 | 0.00015936 | 10932.1 | 10,933 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | success | 8,900,380,372 | N/A | 8,900,369,439 | 101,280,458,487 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| four_factory_m0_center | success | 8,900,380,372 | N/A | 8,900,369,439 | 101,280,371,023 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| four_factory_m0_right | success | 8,900,380,372 | N/A | 8,900,369,439 | 101,280,458,487 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |
| four_factory_m0_far_corner | success | 8,900,380,372 | N/A | 8,900,369,439 | 101,287,827,329 | N/A | 2,018,231,800 | 1,899,586,884 | 96 | 32,448 | 13 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 9,263,739 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| four_factory_m0_center | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 9,263,731 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| four_factory_m0_right | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 9,263,739 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |
| four_factory_m0_far_corner | success | 15 | 10,000 | 814,084 | N/A | 814,083 | 1 | 9,264,413 | N/A | 96 | 32,448 | 13 | 184,600 | 173,748 |

## H5 / 4th(new_2)

### PF-Step Scaling

| PF coeff | PF order | target error | effective blocks | actions |
| --- | --- | --- | --- | --- |
| 3.64607e-05 | 4 | 0.00015936 | 9734.55 | 9,735 |

### Linearly Scaled Resources

| case | status | total runtime topo | vs baseline | total runtime no topo | total qubit volume | qv vs baseline | total magic count | total magic depth | cells | physical qubits | code distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | success | 20,660,541,825 | N/A | 20,660,249,775 | 274,330,664,520 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| four_factory_m0_center | success | 20,660,541,825 | N/A | 20,660,249,775 | 274,330,664,520 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| four_factory_m0_right | success | 20,660,541,825 | N/A | 20,660,249,775 | 274,330,664,520 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |
| four_factory_m0_far_corner | success | 20,660,541,825 | N/A | 20,660,249,775 | 274,460,840,940 | N/A | 4,632,944,910 | 4,393,035,570 | 96 | 43,200 | 15 |

### Single-Step Resources

| case | status | magic period | stock | runtime topo | runtime vs baseline | runtime no topo | runtime diff vs no topo | qubit volume | qv vs baseline | cells | physical qubits | code distance | magic count | magic depth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_factory_m0_left | success | 15 | 10,000 | 2,122,295 | N/A | 2,122,265 | 30 | 28,179,832 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| four_factory_m0_center | success | 15 | 10,000 | 2,122,295 | N/A | 2,122,265 | 30 | 28,179,832 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| four_factory_m0_right | success | 15 | 10,000 | 2,122,295 | N/A | 2,122,265 | 30 | 28,179,832 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
| four_factory_m0_far_corner | success | 15 | 10,000 | 2,122,295 | N/A | 2,122,265 | 30 | 28,193,204 | N/A | 96 | 43,200 | 15 | 475,906 | 451,262 |
