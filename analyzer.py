import os
import numpy as np
import pydantic
from google import genai
from google.genai import types
import simulator

class AnalyzerReport(pydantic.BaseModel):
    quantum_query_complexity: str
    quantum_gate_complexity: str
    classical_complexity: str
    speedup_type: str
    analysis_text: str
    potential_applications: str

class Analyzer:
    def __init__(self, model="gemini-flash-lite-latest"):
        self.model = model
        self.system_instructions = (
            "You are an expert Quantum Complexity Analyzer. You take scaling data "
            "(number of qubits N, circuit depth, gate counts, and success rate) and fit "
            "complexity growth models (Linear, Polynomial, Exponential). You compare "
            "the quantum scaling to classical baselines and write a detailed analysis. "
            "Be mathematically precise and identify if there is an exponential, quadratic, "
            "or linear speedup.\n\n"
            "Additionally, you must write a detailed 'potential_applications' section. In it, "
            "you will map the abstract mathematical structure of the oracle (e.g. modular residue multiplication, "
            "popcount parity, quadratic relations) to real-world software concepts and computer science domains. "
            "Explain how this function relates to areas such as symmetric cryptanalysis (S-box structures, AES, "
            "hash collision vulnerabilities), error-correcting codes, or search optimization, and whether "
            "it could have practical utility."
        )

    async def analyze_scaling(self, problem: dict, scaling_data: list) -> dict:
        prompt = (
            f"Problem Name: {problem.get('problem_name')}\n"
            f"Description: {problem.get('description')}\n\n"
            f"Scaling Data collected from Qiskit simulations:\n"
        )
        for data in scaling_data:
            prompt += (
                f"- N={data['N']} Qubits:\n"
                f"  Success Rate: {data['success_rate']}\n"
                f"  Circuit Depth (non-oracle): {data['depth']}\n"
                f"  Gate Counts: {data['gate_counts']}\n"
                f"  Mid-Gates: {data.get('mid_gates')}\n"
            )
            
        gemini_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=gemini_key)
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instructions,
                response_mime_type="application/json",
                response_schema=AnalyzerReport,
            )
        )
        import json
        return json.loads(response.text)

def collect_scaling_data(problem_proposal: dict) -> list:
    """
    Simulates the proposed problem for multiple values of N to collect scaling data.
    """
    max_N = problem_proposal.get('max_qubits_to_simulate', 3)
    # We simulate for N = 2 up to max_N
    scaling_data = []
    for N in range(2, max_N + 1):
        try:
            res = simulator.run_simulation(problem_proposal, N)
            res['N'] = N
            scaling_data.append(res)
        except Exception as e:
            print(f"Skipping N={N} due to error: {e}")
            
    return scaling_data
