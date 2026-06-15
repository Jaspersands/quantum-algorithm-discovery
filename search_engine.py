import numpy as np
from qiskit import QuantumCircuit
from qiskit import transpile
from qiskit_aer import Aer
import itertools
import os
from concurrent.futures import ProcessPoolExecutor

# Cache Aer backend for faster execution
_backend = Aer.get_backend('statevector_simulator')

def get_statevector(qc):
    """Returns the statevector of a circuit."""
    result = _backend.run(qc).result()
    return result.get_statevector(qc)


def build_oracle(num_qubits, classical_func):
    """
    Builds an oracle circuit:
    |x>|y> -> |x>|y ^ classical_func(x)>
    """
    qc = QuantumCircuit(num_qubits + 1)
    for x in range(2**num_qubits):
        val = classical_func(x)
        if val == 1:
            for i in range(num_qubits):
                if not (x & (1 << i)):
                    qc.x(i)
            qc.mcx(list(range(num_qubits)), num_qubits)
            for i in range(num_qubits):
                if not (x & (1 << i)):
                    qc.x(i)
    return qc


def apply_layer(qc, layer, num_qubits):
    """Applies a layer of gates to the circuit."""
    if len(layer) == num_qubits:
        # Single-qubit gates
        for idx, gate in enumerate(layer):
            if gate == 'H':
                qc.h(idx)
            elif gate == 'X':
                qc.x(idx)
            elif gate == 'Z':
                qc.z(idx)
            elif gate == 'S':
                qc.s(idx)
            elif gate == 'T':
                qc.t(idx)
            # 'I' is identity, do nothing
    elif len(layer) == 3 and layer[0] == 'CX':
        qc.cx(layer[1], layer[2])
    elif len(layer) == 1 and layer[0] == 'DIFF':
        # Standard diffusion operator for Grover's search
        for i in range(num_qubits):
            qc.h(i)
            qc.x(i)
        qc.h(num_qubits - 1)
        qc.mcx(list(range(num_qubits - 1)), num_qubits - 1)
        qc.h(num_qubits - 1)
        for i in range(num_qubits):
            qc.x(i)
            qc.h(i)


def find_orthogonal_secrets(outcomes, num_qubits):
    """
    Finds all secrets s (integers) in 0..2^N-1 that are orthogonal to all outcomes in GF(2).
    A secret s is orthogonal to outcome y if the bitwise dot product s . y = 0 (mod 2).
    """
    orthogonal = []
    for s in range(2**num_qubits):
        is_ortho = True
        for y in outcomes:
            dot = 0
            for i in range(num_qubits):
                if (s & (1 << i)) and (y & (1 << i)):
                    dot ^= 1
            if dot != 0:
                is_ortho = False
                break
        if is_ortho:
            orthogonal.append(s)
    return orthogonal


def evaluate_circuit(num_qubits, pre_gates, post_gates, mid_gates, max_queries, oracle_generator, secrets, requires_linear_solver=False):
    """
    Evaluates how well a circuit template solves the problem, with early pruning support.
    """
    secret_to_outcome = {}
    success_count = 0
    
    # Helper to evaluate a single secret configuration
    def eval_secret(secret):
        qc = QuantumCircuit(num_qubits + 1, num_qubits)
        
        # Target qubit setup (|->)
        qc.x(num_qubits)
        qc.h(num_qubits)
        
        # Apply pre-oracle gates
        for layer in pre_gates:
            apply_layer(qc, layer, num_qubits)
        
        # Oracle and mid-gates loop
        classical_func = oracle_generator(secret, num_qubits)
        oracle_qc = build_oracle(num_qubits, classical_func)
        
        for q in range(max_queries):
            qc.compose(oracle_qc, inplace=True)
            if q < max_queries - 1 and mid_gates:
                for layer in mid_gates:
                    apply_layer(qc, layer, num_qubits)
        
        # Apply post-oracle gates
        for layer in post_gates:
            apply_layer(qc, layer, num_qubits)
        
        sv = get_statevector(qc)
        prob_dict = sv.probabilities_dict()
        
        # Marginalize over target qubit (index num_qubits, which is the MSB in Qiskit state strings)
        input_probs = {}
        for state_str, prob in prob_dict.items():
            input_state = state_str[1:] # remove target qubit
            input_probs[input_state] = input_probs.get(input_state, 0.0) + prob
            
        return input_probs

    # Pass 1: Quick prune with a small deterministic subset of secrets
    quick_secrets = secrets
    if len(secrets) > 6:
        # Sample 4 spread-out secrets
        quick_secrets = [secrets[0], secrets[len(secrets)//3], secrets[2*len(secrets)//3], secrets[-1]]
        # Remove duplicates if any
        quick_secrets = list(dict.fromkeys(quick_secrets))

    # Evaluate quick secrets
    for secret in quick_secrets:
        input_probs = eval_secret(secret)
        if requires_linear_solver:
            high_prob_outcomes = []
            total_prob = 0.0
            sorted_outcomes = sorted(input_probs.items(), key=lambda x: x[1], reverse=True)
            for state_str, prob in sorted_outcomes:
                if prob > 0.05:
                    high_prob_outcomes.append(int(state_str, 2))
                    total_prob += prob
                if total_prob > 0.95:
                    break
            if total_prob < 0.95:
                return 0.0, {}
            ortho_secrets = find_orthogonal_secrets(high_prob_outcomes, num_qubits)
            if secret == 0:
                if ortho_secrets == [0]:
                    success_count += 1
                    secret_to_outcome[secret] = [bin(y)[2:].zfill(num_qubits) for y in high_prob_outcomes]
                else:
                    return 0.0, {}
            else:
                if len(ortho_secrets) == 2 and secret in ortho_secrets:
                    success_count += 1
                    secret_to_outcome[secret] = [bin(y)[2:].zfill(num_qubits) for y in high_prob_outcomes]
                else:
                    return 0.0, {}
        else:
            best_state = max(input_probs, key=input_probs.get)
            max_prob = input_probs[best_state]
            if max_prob > 0.95:
                if best_state in secret_to_outcome.values():
                    return 0.0, {}
                secret_to_outcome[secret] = best_state
                success_count += 1
            else:
                return 0.0, {}

    # Pass 2: Full evaluation for all remaining secrets (only runs if Pass 1 succeeds)
    remaining_secrets = [s for s in secrets if s not in quick_secrets]
    for secret in remaining_secrets:
        input_probs = eval_secret(secret)
        if requires_linear_solver:
            high_prob_outcomes = []
            total_prob = 0.0
            sorted_outcomes = sorted(input_probs.items(), key=lambda x: x[1], reverse=True)
            for state_str, prob in sorted_outcomes:
                if prob > 0.05:
                    high_prob_outcomes.append(int(state_str, 2))
                    total_prob += prob
                if total_prob > 0.95:
                    break
            if total_prob < 0.95:
                return 0.0, {}
            ortho_secrets = find_orthogonal_secrets(high_prob_outcomes, num_qubits)
            if secret == 0:
                if ortho_secrets == [0]:
                    success_count += 1
                    secret_to_outcome[secret] = [bin(y)[2:].zfill(num_qubits) for y in high_prob_outcomes]
                else:
                    return 0.0, {}
            else:
                if len(ortho_secrets) == 2 and secret in ortho_secrets:
                    success_count += 1
                    secret_to_outcome[secret] = [bin(y)[2:].zfill(num_qubits) for y in high_prob_outcomes]
                else:
                    return 0.0, {}
        else:
            best_state = max(input_probs, key=input_probs.get)
            max_prob = input_probs[best_state]
            if max_prob > 0.95:
                if best_state in secret_to_outcome.values():
                    return 0.0, {}
                secret_to_outcome[secret] = best_state
                success_count += 1
            else:
                return 0.0, {}

    success_rate = success_count / len(secrets) if len(secrets) > 0 else 0.0
    return success_rate, secret_to_outcome


def _search_chunk(chunk_args):
    """Worker function for parallel/sequential processing."""
    num_qubits, configs, problem_proposal, gates_to_use, max_queries, requires_linear_solver = chunk_args
    
    # Reconstruct generator functions locally to bypass pickling issues
    local_ns = {}
    exec(problem_proposal['base_function_code'], globals(), local_ns)
    exec(problem_proposal['oracle_generator_code'], globals(), local_ns)
    exec(problem_proposal['secrets_generator_code'], globals(), local_ns)
    
    make_oracle = local_ns.get('make_oracle')
    if not make_oracle:
        for k, v in local_ns.items():
            if callable(v) and ('oracle' in k or 'make' in k):
                make_oracle = v
                break
                
    get_secrets = local_ns.get('get_secrets')
    if not get_secrets:
        for k, v in local_ns.items():
            if callable(v) and ('secret' in k or 'get' in k):
                get_secrets = v
                break
                
    secrets = get_secrets(num_qubits)
    
    best_rate = 0.0
    best_config = None
    
    for pre, post, mid in configs:
        rate, mapping = evaluate_circuit(
            num_qubits, pre, post, mid, max_queries,
            make_oracle, secrets, requires_linear_solver
        )
        if rate > best_rate:
            best_rate = rate
            best_config = (pre, post, mid, mapping)
            if best_rate >= 1.0:
                return best_rate, best_config
                
    return best_rate, best_config


def search_circuits(num_qubits, problem_proposal, gates_to_use=None, max_queries=1, requires_linear_solver=False):
    """
    Searches the space of gate layers for a perfect mapping.
    """
    if not gates_to_use:
        gates_to_use = ['H', 'I']
        
    # Generate all single-qubit layers
    single_gates = [g for g in gates_to_use if g not in ['CX', 'DIFF']]
    if not single_gates:
        single_gates = ['I']
    single_qubit_layers = list(itertools.product(single_gates, repeat=num_qubits))
    
    # Generate CNOT layers
    cnot_layers = []
    if 'CX' in gates_to_use:
        for i in range(num_qubits - 1):
            cnot_layers.append(('CX', i, i + 1))
            cnot_layers.append(('CX', i + 1, i))
            
    # Generate DIFF layers
    diff_layers = []
    if 'DIFF' in gates_to_use:
        diff_layers.append(('DIFF',))
        
    all_layers = single_qubit_layers + cnot_layers + diff_layers
    
    # Pre combinations: 1 layer of single-qubit gates
    pre_combinations = [[layer] for layer in single_qubit_layers]
    
    # Mid combinations: 1 layer of any gate (only if queries > 1)
    if max_queries > 1:
        mid_combinations = [[layer] for layer in all_layers]
    else:
        mid_combinations = [[]]
        
    # Post combinations: 1 layer by default, or up to 2 layers if CX is allowed
    post_combinations = [[layer] for layer in all_layers]
    if 'CX' in gates_to_use:
        for l1 in all_layers:
            for l2 in all_layers:
                post_combinations.append([l1, l2])
                
    # Generate Cartesian product of configurations using memory-efficient index sampling if needed
    total_configs = len(pre_combinations) * len(post_combinations) * len(mid_combinations)
    MAX_CONFIGS = 50000
    
    if total_configs > MAX_CONFIGS:
        print(f"[!] Search space too large ({total_configs} configs). Sub-sampling to {MAX_CONFIGS} configurations...")
        import random
        random.seed(42)
        
        # Keep the simplest configurations (the first 10,000) and sample the rest
        keep_count = min(10000, total_configs)
        sampled_indices = list(range(keep_count))
        
        if total_configs > keep_count:
            remaining_sample_count = MAX_CONFIGS - keep_count
            sampled_indices.extend(random.sample(range(keep_count, total_configs), remaining_sample_count))
            
        configs = []
        len_mid = len(mid_combinations)
        len_post = len(post_combinations)
        for idx in sampled_indices:
            mid_idx = idx % len_mid
            rem = idx // len_mid
            post_idx = rem % len_post
            pre_idx = rem // len_post
            configs.append((pre_combinations[pre_idx], post_combinations[post_idx], mid_combinations[mid_idx]))
    else:
        configs = []
        for pre in pre_combinations:
            for post in post_combinations:
                for mid in mid_combinations:
                    configs.append((pre, post, mid))
                
    # Run sequentially (multiprocessing causes OpenMP deadlocks in Qiskit Aer backend)
    best_rate, best_config = _search_chunk((num_qubits, configs, problem_proposal, gates_to_use, max_queries, requires_linear_solver))
    return best_rate, best_config


def get_circuit_properties(num_qubits, pre_gates, post_gates, mid_gates, max_queries):
    """
    Returns the depth and gate counts of the non-oracle part of the circuit.
    """
    qc = QuantumCircuit(num_qubits + 1, num_qubits)
    qc.x(num_qubits)
    qc.h(num_qubits)
    
    if pre_gates:
        for layer in pre_gates:
            apply_layer(qc, layer, num_qubits)
            
    if max_queries > 1 and mid_gates:
        for q in range(max_queries - 1):
            for layer in mid_gates:
                apply_layer(qc, layer, num_qubits)
                
    if post_gates:
        for layer in post_gates:
            apply_layer(qc, layer, num_qubits)
            
    qc = transpile(qc, basis_gates=['h', 'x', 'cx', 's', 'z', 't'])
    depth = qc.depth()
    gate_counts = qc.count_ops()
    return depth, dict(gate_counts)
