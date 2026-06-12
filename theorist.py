import os
import pydantic
from google import genai
from google.genai import types

class ProblemProposal(pydantic.BaseModel):
    problem_name: str
    description: str
    base_function_code: str
    oracle_generator_code: str
    secrets_generator_code: str
    max_qubits_to_simulate: int
    gates_to_use: list[str]
    max_queries: int
    requires_linear_solver: bool

class Theorist:
    def __init__(self, model="gemini-2.5-flash-lite"):
        self.model = model
        self.system_instructions = (
            "You are an expert Quantum Complexity Theorist. Your task is to propose "
            "STRICTLY NOVEL, custom, or non-textbook oracle-based problems (NOT standard textbook "
            "ones like Bernstein-Vazirani, Simon's, Deutsch-Jozsa, or Grover's). Propose creative "
            "custom functions where a quantum speedup might be discovered by the search engine. "
            "To allow automated complexity scaling analysis, you MUST define your functions "
            "parameterized by the number of qubits N. Specifically, you must provide:\n"
            "1. base_function_code: A string containing a function `g(x, N)` representing a "
            "classical function on an N-bit integer x.\n"
            "2. oracle_generator_code: A string containing a function `make_oracle(secret, N)` "
            "which returns a classical function `f(x)` that takes an N-bit integer x and returns 0 or 1.\n"
            "3. secrets_generator_code: A string containing a function `get_secrets(N)` which "
            "returns a list of integers representing all possible secret values for N qubits.\n"
            "4. max_qubits_to_simulate: An integer (MUST be exactly 3 to prevent CPU throttling on the free VM) indicating the safe upper "
            "bound of N to simulate in a brute-force search.\n"
            "5. gates_to_use: A list of gate names allowed in the search. Keep it as small as possible to avoid search explosion. "
            "Choose from: 'H' (Hadamard), 'I' (Identity), 'X' (Not), 'Z' (Phase flip), 'S' (Phase), 'T' (T/8 Phase), 'CX' (Adjacent CNOT), "
            "and 'DIFF' (Grover's diffusion operator).\n"
            "  - For Bernstein-Vazirani: ['H', 'I']\n"
            "  - For Simon's algorithm: ['H', 'I', 'CX']\n"
            "  - For Grover's search: ['H', 'I', 'X', 'Z', 'DIFF']\n"
            "6. max_queries: An integer (usually 1, but up to 2 for multi-query algorithms like Grover's).\n"
            "7. requires_linear_solver: A boolean indicating whether finding the secret requires Simon-like GF(2) linear solver post-processing "
            "where measurement outcomes satisfy y . s = 0 (mod 2).\n"
            "8. Crucially, the Python code strings in base_function_code, oracle_generator_code, and secrets_generator_code MUST be valid, "
            "executable Python 3 code. They must NOT contain any backslashes, LaTeX math syntax (such as \\cdot), or invalid escape sequences "
            "in the comments or code. Keep them extremely clean and simple."
        )

    async def propose_problem(self, prompt: str) -> dict:
        gemini_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=gemini_key)
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instructions,
                response_mime_type="application/json",
                response_schema=ProblemProposal,
            )
        )
        import json
        return json.loads(response.text)

