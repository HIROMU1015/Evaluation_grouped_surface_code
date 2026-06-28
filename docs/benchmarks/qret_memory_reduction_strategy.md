# qret H4/H5 Memory Reduction Strategy

Only H4 and H5 were observed. H6, H7, H8, and H9 were not executed.

## Required Execution Flags

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.
- Holder note: final code uses list+optional-handle storage after C++ destructor-safety validation; H5 was not rerun after this holder-only fix to obey the run cap.

## Observed H4/H5 Component Estimates

| case | variant | classification | component | MB |
| ---- | ------- | -------------- | --------- | --: |
| H4 `4th(new_2)` | legacy | estimated | instruction_object | 51.8 |
| H4 `4th(new_2)` | legacy | estimated | operand_containers | 19.6 |
| H4 `4th(new_2)` | legacy | estimated | path_storage | 26.9 |
| H4 `4th(new_2)` | legacy | estimated | instruction_list_nodes | 13.1 |
| H4 `4th(new_2)` | legacy | estimated | inverse_map | 0.0 |
| H4 `4th(new_2)` | legacy | estimated | metadata | 8.7 |
| H4 `4th(new_2)` | legacy | estimated | routing_temporary | 8.3 |
| H4 `4th(new_2)` | legacy | observed | python_parent | 1.2 |
| H4 `4th(new_2)` | candidate | estimated | instruction_object | 51.8 |
| H4 `4th(new_2)` | candidate | estimated | operand_containers | 19.6 |
| H4 `4th(new_2)` | candidate | estimated | path_storage | 1.5 |
| H4 `4th(new_2)` | candidate | estimated | instruction_list_nodes | 13.1 |
| H4 `4th(new_2)` | candidate | estimated | inverse_map | 0.0 |
| H4 `4th(new_2)` | candidate | estimated | metadata | 8.7 |
| H4 `4th(new_2)` | candidate | estimated | routing_temporary | 8.3 |
| H4 `4th(new_2)` | candidate | observed | python_parent | 1.2 |
| H5 `4th(new_2)` | legacy | estimated | instruction_object | 136.0 |
| H5 `4th(new_2)` | legacy | estimated | operand_containers | 51.4 |
| H5 `4th(new_2)` | legacy | estimated | path_storage | 68.4 |
| H5 `4th(new_2)` | legacy | estimated | instruction_list_nodes | 34.3 |
| H5 `4th(new_2)` | legacy | estimated | inverse_map | 0.0 |
| H5 `4th(new_2)` | legacy | estimated | metadata | 22.9 |
| H5 `4th(new_2)` | legacy | estimated | routing_temporary | 19.9 |
| H5 `4th(new_2)` | legacy | observed | python_parent | 1.2 |
| H5 `4th(new_2)` | legacy | estimated | instruction_object | 136.0 |
| H5 `4th(new_2)` | legacy | estimated | operand_containers | 51.4 |
| H5 `4th(new_2)` | legacy | estimated | path_storage | 68.4 |
| H5 `4th(new_2)` | legacy | estimated | instruction_list_nodes | 34.3 |
| H5 `4th(new_2)` | legacy | estimated | inverse_map | 0.0 |
| H5 `4th(new_2)` | legacy | estimated | metadata | 22.9 |
| H5 `4th(new_2)` | legacy | estimated | routing_temporary | 19.9 |
| H5 `4th(new_2)` | legacy | observed | python_parent | 1.2 |
| H5 `4th(new_2)` | candidate | estimated | instruction_object | 136.0 |
| H5 `4th(new_2)` | candidate | estimated | operand_containers | 51.4 |
| H5 `4th(new_2)` | candidate | estimated | path_storage | 5.0 |
| H5 `4th(new_2)` | candidate | estimated | instruction_list_nodes | 34.3 |
| H5 `4th(new_2)` | candidate | estimated | inverse_map | 0.0 |
| H5 `4th(new_2)` | candidate | estimated | metadata | 22.9 |
| H5 `4th(new_2)` | candidate | estimated | routing_temporary | 19.9 |
| H5 `4th(new_2)` | candidate | observed | python_parent | 1.2 |
| H5 `4th(new_2)` | candidate | estimated | instruction_object | 136.0 |
| H5 `4th(new_2)` | candidate | estimated | operand_containers | 51.4 |
| H5 `4th(new_2)` | candidate | estimated | path_storage | 5.0 |
| H5 `4th(new_2)` | candidate | estimated | instruction_list_nodes | 34.3 |
| H5 `4th(new_2)` | candidate | estimated | inverse_map | 0.0 |
| H5 `4th(new_2)` | candidate | estimated | metadata | 22.9 |
| H5 `4th(new_2)` | candidate | estimated | routing_temporary | 19.9 |
| H5 `4th(new_2)` | candidate | observed | python_parent | 1.2 |

## H9 Estimates

The models are instruction-count ratio, instruction-type ratio, bytes-per-instruction, and component-growth. Scenarios combine those model outputs instead of mechanically applying a single ratio.

- observed classification present: `observed`
- estimated classification present: `estimated`
- theoretical classification present: `theoretical`

| scenario | variant | classification | component | estimated MB |
| -------- | ------- | -------------- | --------- | -----------: |
| central | candidate | estimated | instruction_object | 6494.0 |
| central | candidate | estimated | operand_containers | 2453.6 |
| central | candidate | estimated | path_storage | 242.0 |
| central | candidate | estimated | instruction_list_nodes | 1638.9 |
| central | candidate | estimated | inverse_map | 0.0 |
| central | candidate | estimated | metadata | 1092.6 |
| central | candidate | estimated | routing_temporary | 949.2 |
| central | candidate | estimated | python_parent | 59.7 |
| central | candidate | estimated | total | 12930.1 |
| central | production | estimated | instruction_object | 6464.2 |
| central | production | estimated | operand_containers | 2440.5 |
| central | production | estimated | path_storage | 3204.0 |
| central | production | estimated | instruction_list_nodes | 1637.1 |
| central | production | estimated | inverse_map | 0.0 |
| central | production | estimated | metadata | 1091.4 |
| central | production | estimated | routing_temporary | 930.8 |
| central | production | estimated | python_parent | 58.5 |
| central | production | estimated | total | 15826.5 |
| conservative | candidate | estimated | instruction_object | 5513.7 |
| conservative | candidate | estimated | operand_containers | 2083.2 |
| conservative | candidate | estimated | path_storage | 204.5 |
| conservative | candidate | estimated | instruction_list_nodes | 1391.5 |
| conservative | candidate | estimated | inverse_map | 0.0 |
| conservative | candidate | estimated | metadata | 927.7 |
| conservative | candidate | estimated | routing_temporary | 806.0 |
| conservative | candidate | estimated | python_parent | 50.7 |
| conservative | candidate | estimated | total | 10977.3 |
| conservative | production | estimated | instruction_object | 5475.5 |
| conservative | production | estimated | operand_containers | 2065.5 |
| conservative | production | estimated | path_storage | 2672.4 |
| conservative | production | estimated | instruction_list_nodes | 1391.5 |
| conservative | production | estimated | inverse_map | 0.0 |
| conservative | production | estimated | metadata | 927.7 |
| conservative | production | estimated | routing_temporary | 776.4 |
| conservative | production | estimated | python_parent | 48.8 |
| conservative | production | estimated | total | 13357.9 |
| upper | candidate | estimated | instruction_object | 8226.8 |
| upper | candidate | estimated | operand_containers | 3108.3 |
| upper | candidate | estimated | path_storage | 863.5 |
| upper | candidate | estimated | instruction_list_nodes | 2076.2 |
| upper | candidate | estimated | inverse_map | 0.0 |
| upper | candidate | estimated | metadata | 1384.2 |
| upper | candidate | estimated | routing_temporary | 1202.5 |
| upper | candidate | estimated | python_parent | 75.6 |
| upper | candidate | estimated | total | 16937.2 |
| upper | production | estimated | instruction_object | 8126.5 |
| upper | production | estimated | operand_containers | 3070.4 |
| upper | production | estimated | path_storage | 4088.9 |
| upper | production | estimated | instruction_list_nodes | 2050.9 |
| upper | production | estimated | inverse_map | 0.0 |
| upper | production | estimated | metadata | 1367.3 |
| upper | production | estimated | routing_temporary | 1187.9 |
| upper | production | estimated | python_parent | 74.7 |
| upper | production | estimated | total | 19966.6 |

## Candidate Comparison

| scenario | classification | candidate saving MB | candidate saving % |
| -------- | -------------- | ------------------: | -----------------: |
| central | theoretical | 2896.4 | 18.301 |
| conservative | theoretical | 2380.6 | 17.821 |
| upper | theoretical | 3029.4 | 15.172 |

## Next Candidates

1. If exact interning passes the H5 gate, keep it as the production candidate and next attack non-path operand containers.
2. If path storage no longer dominates, evaluate instruction/list-node flattening with H5-only A/B; H9 impact remains model-only.
