import os
import json
import subprocess
from datetime import datetime

def run_git_push():
    try:
        # Check if there are changes to status.json, history.json, or queue.json
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status.stdout.strip():
            # No changes
            return
        
        # Add updated files
        subprocess.run(['git', 'add', 'status.json', 'history.json', 'queue.json'], check=True)
        
        # Commit
        subprocess.run(['git', 'commit', '-m', 'Web Update: status and logs'], check=True)
        
        # Push (the origin remote already has the token embedded in the URL)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        print("[*] Successfully pushed web updates to GitHub.")
    except Exception as e:
        print(f"[!] Git push failed: {e}")

def update_status(status_str, stage_str=None, problem_name=None, description=None, next_run_at=None):
    data = {
        "status": status_str,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }
    if status_str == 'searching':
        data["current_run"] = {
            "problem_name": problem_name,
            "description": description,
            "stage": stage_str,
            "started_at": datetime.utcnow().isoformat() + "Z"
        }
    elif status_str == 'sleeping' and next_run_at:
        data["next_run_at"] = next_run_at
        
    with open('status.json', 'w') as f:
        json.dump(data, f, indent=2)
        
    run_git_push()

def append_history(proposal, target_data, synthesis_report, analysis_report):
    # Load existing history
    history = []
    if os.path.exists('history.json'):
        try:
            with open('history.json') as f:
                history = json.load(f)
        except Exception:
            history = []
            
    run_entry = {
        "problem_name": proposal.get('problem_name', 'Quantum Exploration'),
        "description": proposal.get('description', ''),
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "success_rate": target_data.get('success_rate', 0.0),
        "quantum_query_complexity": analysis_report.get('quantum_query_complexity', 'N/A'),
        "quantum_gate_complexity": analysis_report.get('quantum_gate_complexity', 'N/A'),
        "speedup_type": analysis_report.get('speedup_type', 'N/A'),
        "synthesis_code": synthesis_report.get('circuit_code', ''),
        "analysis_text": analysis_report.get('analysis_text', ''),
        "potential_applications": analysis_report.get('potential_applications', 'No practical application mapping available yet.'),
        "base_function_code": proposal.get('base_function_code', ''),
        "oracle_generator_code": proposal.get('oracle_generator_code', '')
    }
    
    # Prepend to history so latest is first
    history.insert(0, run_entry)
    
    with open('history.json', 'w') as f:
        json.dump(history, f, indent=2)
        
    run_git_push()

def update_queue(backlog_items):
    with open('queue.json', 'w') as f:
        json.dump(backlog_items, f, indent=2)
        
    run_git_push()
