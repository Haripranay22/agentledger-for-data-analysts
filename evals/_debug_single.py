"""Quick debug: run scn_001 through the full eval pipeline to expose the real error."""
import sys, traceback, uuid, yaml
sys.path.insert(0, "src")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

# runner.py lives in evals/ — import by path
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("runner", pathlib.Path("evals/runner.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

with open("evals/scenarios/scn_001_stable_w2.yaml") as f:
    scn = yaml.safe_load(f)

print("Running:", scn["scenario_id"])
try:
    result = runner.run_scenario(scn)
    print("Result:", result)
except Exception as e:
    traceback.print_exc()
    print("\nERROR TYPE:", type(e).__name__)
    print("ERROR MSG:", str(e)[:800])
