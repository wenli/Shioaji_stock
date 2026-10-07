import json

log_path = r"C:\Users\wenli\.gemini\antigravity-ide\brain\8915edc2-1075-4b2e-8b8d-d54860e449f9\.system_generated\logs\transcript_full.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        if "smc_dr_gw_matrix_engine.py" in line and '"write_to_file"' in line:
            obj = json.loads(line)
            for tc in obj.get("tool_calls", []):
                if "smc_dr_gw_matrix_engine.py" in str(tc):
                    code = tc["args"]["CodeContent"]
                    print(code[2000:6000])
            break
