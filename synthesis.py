import os
import pydantic
from google import genai
from google.genai import types

class SynthesisReport(pydantic.BaseModel):
    circuit_code: str
    explanation: str
    is_valid: bool

class Synthesizer:
    def __init__(self, model="gemini-2.5-flash-lite"):
        self.model = model
        self.system_instructions = (
            "You are an expert Quantum Circuit Synthesizer. You take a problem proposal "
            "and the results of a classical search for quantum circuits (pre-gates, post-gates, "
            "mid-gates, and mapping). Your job is to:\n"
            "1. Provide a clean Python code snippet to reconstruct the full Qiskit circuit. If multi-query "
            "was used, show the alternating oracle and mid-gates layers. If Simon's solver was used, show "
            "how the classical GF(2) linear system is solved.\n"
            "2. Provide a clear explanation of how the pre-gates prepare the input state, "
            "how the oracle performs phase kickback or query encoding, how mid-gates (e.g. diffusion) act between "
            "queries, and how the post-gates create constructive/destructive interference to resolve or prepare "
            "the system of equations for the secret.\n"
            "3. Set is_valid to True if a successful circuit (success_rate = 1.0) was found, "
            "otherwise False."
        )

    async def generate_report(self, problem: dict, search_results: dict) -> dict:
        prompt = (
            f"Problem Proposed:\n"
            f"Name: {problem.get('problem_name')}\n"
            f"Description: {problem.get('description')}\n"
            f"Num Qubits: {problem.get('num_qubits')}\n"
            f"Base Function Code: {problem.get('base_function_code')}\n"
            f"Oracle Generator Code: {problem.get('oracle_generator_code')}\n\n"
            f"Search Results:\n"
            f"Success Rate: {search_results.get('success_rate')}\n"
            f"Pre-Gates: {search_results.get('pre_gates')}\n"
            f"Mid-Gates: {search_results.get('mid_gates')}\n"
            f"Post-Gates: {search_results.get('post_gates')}\n"
            f"Mapping: {search_results.get('mapping')}\n"
        )

        gemini_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=gemini_key)
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instructions,
                response_mime_type="application/json",
                response_schema=SynthesisReport,
            )
        )
        import json
        return json.loads(response.text)
