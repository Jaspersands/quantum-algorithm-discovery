import asyncio
import os
import json
import traceback
from theorist import Theorist
from synthesis import Synthesizer
from analyzer import Analyzer, collect_scaling_data
import web_updater

MOCK_PROPOSAL = {
    "problem_name": "Bernstein-Vazirani",
    "description": "Find a hidden bitstring s in a function f(x) = s * x (mod 2).",
    "base_function_code": (
        "def g(x, N):\n"
        "    return 0\n"
    ),
    "oracle_generator_code": (
        "def make_oracle(secret, N):\n"
        "    def f(x):\n"
        "        dot = 0\n"
        "        for i in range(N):\n"
            "            if (secret & (1 << i)) and (x & (1 << i)):\n"
            "                dot ^= 1\n"
        "        return dot\n"
        "    return f\n"
    ),
    "secrets_generator_code": (
        "def get_secrets(N):\n"
        "    return list(range(2**N))\n"
    ),
    "max_qubits_to_simulate": 4
}

async def safe_agent_call(func, *args, max_retries=7, initial_delay=60):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return await func(*args)
        except Exception as e:
            err_str = str(e).lower()
            print(f"[DEBUG] safe_agent_call caught exception: {type(e)}: {e}")
            if "429" in err_str or "quota" in err_str or "limit" in err_str or "resource_exhausted" in err_str or "503" in err_str or "unavailable" in err_str:
                print(f"[!] Rate limit or 503 (429/503) hit. Waiting {delay} seconds before retry (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 120)  # Exponential backoff up to 120s
            else:
                raise e
    raise RuntimeError("Failed after maximum retries due to rate limiting.")

async def main():
    print("==================================================")
    print("Starting Quantum Algorithm Discovery Orchestrator")
    print("==================================================")

    # Load .env file if it exists
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.strip().split("=", 1)
                    val = val.strip("'\"")
                    os.environ[key] = val

    gemini_key = os.environ.get("GEMINI_API_KEY")
    is_mock = not gemini_key

    # Initialize Agents
    print("[1/5] Initializing Theorist, Synthesizer, and Analyzer agents...")
    theorist = None
    synthesizer = None
    analyzer = None
    
    if not is_mock:
        try:
            theorist = Theorist(model="gemini-2.5-flash")
            synthesizer = Synthesizer(model="gemini-flash-lite-latest")
            analyzer = Analyzer(model="gemini-flash-lite-latest")
        except Exception as e:
            print(f"[!] Failed to initialize agent clients: {e}. Falling back to mock mode.")
            is_mock = True

    # Step 1: Propose Problem
    print("\n[2/5] Querying Theorist agent for a new candidate quantum problem...")
    web_updater.update_status('searching', 'theorist', 'Quantum Algorithm Proposal', 'Querying Theorist for a new quantum problem...')
    if is_mock:
        print("[!] GEMINI_API_KEY not found or agents failed to start.")
        print("[!] Falling back to mock Theorist Agent for Bernstein-Vazirani to test simulation pipeline...")
        proposal = MOCK_PROPOSAL
        print(f"Problem proposed (MOCK): '{proposal.get('problem_name')}'")
        print(f"Description: {proposal.get('description')}")
    else:
        # Load existing problems from history.json to avoid duplicates, and block classic textbook algorithms
        existing_problems = [
            "Bernstein-Vazirani",
            "Bernstein-Vazirani Problem",
            "Simon's Period-Finding Problem",
            "Simon's Algorithm",
            "Deutsch-Jozsa",
            "Deutsch-Jozsa Algorithm",
            "Grover's Search",
            "Grover's Algorithm",
            "Hidden Shift",
            "Hidden Shift Problem"
        ]
        if os.path.exists('history.json'):
            try:
                with open('history.json') as f:
                    history_data = json.load(f)
                    existing_problems.extend([item.get('problem_name') for item in history_data if item.get('problem_name')])
            except Exception as e:
                print(f"[!] Could not load search history: {e}")
                
        avoid_list = ", ".join([f"'{name}'" for name in set(existing_problems)]) if existing_problems else "None"
        
        prompt = (
            "Propose a STRICTLY NOVEL, custom, or non-textbook oracle-based quantum problem (e.g., "
            "a custom boolean function relation, a customized group action, or a non-standard shift "
            "that is NOT a textbook algorithm). Make sure to configure "
            "the required gate set (gates_to_use), max queries (max_queries), and linear solver flag "
            "(requires_linear_solver) correctly in your response schema to make the automated circuit "
            "search successful and efficient. Keep functions simple and syntax-error free.\n\n"
            f"CRITICAL: Do NOT propose any of the following problems that we have already searched or standard textbook ones: {avoid_list}."
        )
        try:
            proposal = await safe_agent_call(theorist.propose_problem, prompt)
            proposal['max_qubits_to_simulate'] = min(proposal.get('max_qubits_to_simulate', 3), 3)
            
            # Helper to strip markdown code fences from LLM responses
            def clean_code(code_str):
                if not code_str:
                    return ""
                code_str = code_str.strip()
                if code_str.startswith("```"):
                    lines = code_str.splitlines()
                    start_idx = 1 if lines[0].startswith("```") else 0
                    end_idx = len(lines) - 1 if lines[-1].startswith("```") else len(lines)
                    code_str = "\n".join(lines[start_idx:end_idx]).strip()
                return code_str

            proposal['base_function_code'] = clean_code(proposal.get('base_function_code', ''))
            proposal['oracle_generator_code'] = clean_code(proposal.get('oracle_generator_code', ''))
            proposal['secrets_generator_code'] = clean_code(proposal.get('secrets_generator_code', ''))

            print(f"Problem proposed successfully: '{proposal.get('problem_name')}'")
            print(f"Description: {proposal.get('description')}")
            print(f"Simulating up to N = {proposal.get('max_qubits_to_simulate')} qubits (capped at 3 for VM performance).")
        except Exception as e:
            print(f"[!] Error during problem proposal: {e}. Falling back to mock proposal.")
            proposal = MOCK_PROPOSAL
            is_mock = True

    # Step 2: Simulate and Collect Scaling Data
    print("\n[3/5] Simulating quantum circuit search across different qubit scales...")
    web_updater.update_status('searching', 'simulating', proposal.get('problem_name', 'Quantum Exploration'), proposal.get('description', ''))
    try:
        scaling_data = collect_scaling_data(proposal)
        if not scaling_data:
            print("No scaling data could be collected. Search failed to find a valid circuit.")
            return
        print(f"Collected scaling data for {len(scaling_data)} sizes:")
        for data in scaling_data:
            print(f"  N={data['N']}: Success Rate={data['success_rate']}, Depth={data['depth']}, Gates={data['gate_counts']}")
    except Exception as e:
        print(f"Error during simulation/scaling collection: {e}")
        traceback.print_exc()
        return

    # Wait for rate limit window to clear before calling the Synthesizer agent
    if not is_mock:
        print("\n[*] Sleeping 60 seconds before calling Synthesizer agent to prevent rate limiting...")
        await asyncio.sleep(60)

    # Step 3: Synthesis Report
    print("\n[4/5] Running Synthesizer agent to document the circuit and explanation...")
    web_updater.update_status('searching', 'synthesizing', proposal.get('problem_name', 'Quantum Exploration'), proposal.get('description', ''))
    target_data = scaling_data[-1]
    
    if is_mock:
        synthesis_report = {
            "is_valid": True,
            "explanation": (
                "The Bernstein-Vazirani algorithm prepares the input qubits in |+>^N "
                "and the target qubit in |->. Applying the oracle creates a phase kickback "
                "(-1)^(s * x) on the input state. Applying Hadamard gates to the input "
                "qubits performs a Fourier transform, directly outputting the secret s."
            ),
            "circuit_code": (
                "from qiskit import QuantumCircuit\n"
                "qc = QuantumCircuit(N + 1, N)\n"
                "qc.x(N)\n"
                "qc.h(range(N + 1))\n"
                "qc.compose(oracle, inplace=True)\n"
                "qc.h(range(N))\n"
                "qc.measure(range(N), range(N))\n"
            )
        }
        print("Synthesizer Report generated (MOCK):")
        print(f"  Valid Circuit Found: {synthesis_report.get('is_valid')}")
        print("  Explanation Summary:")
        print(f"    {synthesis_report.get('explanation')[:300]}...")
    else:
        try:
            synthesis_report = await safe_agent_call(synthesizer.generate_report, proposal, target_data)
            print("Synthesizer Report generated:")
            print(f"  Valid Circuit Found: {synthesis_report.get('is_valid')}")
            print("  Explanation Summary:")
            print(f"    {synthesis_report.get('explanation')[:300]}...")
        except Exception as e:
            print(f"[!] Error during synthesis report generation: {e}")
            synthesis_report = {"is_valid": False, "explanation": "Failed to generate", "circuit_code": ""}

    # Wait for rate limit window to clear before calling the Analyzer agent
    if not is_mock:
        print("\n[*] Sleeping 60 seconds before calling Complexity Analyzer agent to prevent rate limiting...")
        await asyncio.sleep(60)

    # Step 4: Complexity Analysis
    print("\n[5/5] Running Complexity Analyzer agent to evaluate scaling and speedup...")
    web_updater.update_status('searching', 'analyzing', proposal.get('problem_name', 'Quantum Exploration'), proposal.get('description', ''))
    if is_mock:
        analysis_report = {
            "quantum_query_complexity": "O(1)",
            "quantum_gate_complexity": "O(N)",
            "classical_complexity": "O(N)",
            "speedup_type": "Linear",
            "analysis_text": (
                "The quantum algorithm runs in 1 query, whereas classical deterministic "
                "search requires N queries. Thus, we achieve a linear speedup. "
                "The gate complexity is linear O(N) due to the single-qubit Hadamard gates "
                "applied before and after the oracle."
            )
        }
        print("Complexity Analysis completed (MOCK):")
        print(f"  Quantum Query Complexity: {analysis_report.get('quantum_query_complexity')}")
        print(f"  Quantum Gate Complexity: {analysis_report.get('quantum_gate_complexity')}")
        print(f"  Classical Complexity: {analysis_report.get('classical_complexity')}")
        print(f"  Speedup Type: {analysis_report.get('speedup_type')}")
        print("\nAnalysis Text:")
        print(analysis_report.get('analysis_text'))
    else:
        try:
            analysis_report = await safe_agent_call(analyzer.analyze_scaling, proposal, scaling_data)
            print("Complexity Analysis completed:")
            print(f"  Quantum Query Complexity: {analysis_report.get('quantum_query_complexity')}")
            print(f"  Quantum Gate Complexity: {analysis_report.get('quantum_gate_complexity')}")
            print(f"  Classical Complexity: {analysis_report.get('classical_complexity')}")
            print(f"  Speedup Type: {analysis_report.get('speedup_type')}")
            print("\nAnalysis Text:")
            print(analysis_report.get('analysis_text'))
        except Exception as e:
            print(f"[!] Error during complexity analysis: {e}")
            analysis_report = {}

    # Save results
    problem_slug = proposal.get('problem_name', 'algorithm').lower().replace(' ', '_')
    results_dir = os.path.join("results", problem_slug)
    os.makedirs(results_dir, exist_ok=True)
    
    with open(os.path.join(results_dir, "proposal.json"), "w") as f:
        json.dump(proposal, f, indent=2)
        
    with open(os.path.join(results_dir, "scaling.json"), "w") as f:
        json.dump(scaling_data, f, indent=2)
        
    with open(os.path.join(results_dir, "synthesis.json"), "w") as f:
        json.dump(synthesis_report, f, indent=2)
        
    with open(os.path.join(results_dir, "analysis.json"), "w") as f:
        json.dump(analysis_report, f, indent=2)

    web_updater.append_history(proposal, target_data, synthesis_report, analysis_report)
    backlog = [
        {"theme": f"Variations of {proposal.get('problem_name', 'current problem')}", "priority": "High"},
        {"theme": "Grover search under alternative diffusion operators", "priority": "Medium"},
        {"theme": "Multi-query Period Finding with S/T gates", "priority": "Low"}
    ]
    web_updater.update_queue(backlog)
    web_updater.update_status('idle')

    print(f"\nAll reports and code saved to: {results_dir}/")
    print("==================================================")
    print("Discovery Loop Completed Successfully!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
