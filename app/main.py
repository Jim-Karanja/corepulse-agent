import os
import subprocess
import psutil
from dataclasses import dataclass
from kubernetes import client, config
from loguru import logger
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

@dataclass
class Deps:
    server_name: str

# --- 1. DYNAMIC MODEL PICKER ---
def get_model():
    provider = os.getenv('MODEL_PROVIDER', 'openai').lower()
    
    if provider == 'openai':
        return 'openai:gpt-4o'
    elif provider == 'anthropic':
        return 'anthropic:claude-3-5-sonnet-latest'
    elif provider == 'gemini':
        return 'google-gla:gemini-1.5-pro'
    elif provider == 'ollama':
        # Local DeepSeek or Llama via Ollama
        return OpenAIModel(
            model_name=os.getenv('OLLAMA_MODEL', 'deepseek-r1'),
            base_url=os.getenv('OLLAMA_BASE_URL', 'http://ollama-service:11434/v1'),
            api_key='ollama' 
        )
    return 'openai:gpt-4o'

# --- 2. KUBERNETES INITIALIZATION ---
try:
    config.load_incluster_config()
    k8s_v1 = client.CoreV1Api()
    logger.info("Kubernetes In-Cluster Config Loaded.")
except Exception as e:
    k8s_v1 = None
    logger.warning(f"K8s not detected (Local Mode): {e}")

# --- 3. AGENT DEFINITION ---
agent = Agent(
    get_model(),
    deps_type=Deps,
    system_prompt=(
        "You are CorePulse, an SRE Agent. "
        "Logic: 1. Check Hardware (Disk/Temp) -> 2. Check Network -> 3. Check K8s Pods. "
        "If hardware is failing, do not restart software; alert the human."
    ),
)

# --- 4. DIAGNOSTIC TOOLS ---
@agent.tool_plain
def check_hardware_health() -> str:
    """Checks physical disk health using smartctl on /dev/sda."""
    try:
        # Check /host/dev because of our Kubernetes hostPath volume mount
        cmd = ["smartctl", "-H", "/host/dev/sda"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if "PASSED" in res.stdout:
            return "Physical Disk Health: OK (SMART Status PASSED)"
        return f"CRITICAL: Disk health failure detected! {res.stdout}"
    except Exception as e:
        return f"Hardware check failed: {str(e)}"

@agent.tool_plain
def get_cluster_status() -> str:
    """Lists unhealthy pods using ServiceAccount permissions."""
    if not k8s_v1:
        return "Cannot check cluster: K8s API unreachable."
    try:
        pods = k8s_v1.list_pod_for_all_namespaces()
        unhealthy = [p.metadata.name for p in pods.items if p.status.phase != "Running"]
        return f"Unhealthy pods: {unhealthy}" if unhealthy else "All pods Running."
    except Exception as e:
        return f"K8s API error: {str(e)}"

@agent.tool_plain
def check_network() -> str:
    """Checks network latency and connectivity."""
    try:
        res = subprocess.run(["ping", "-c", "3", "8.8.8.8"], capture_output=True, text=True)
        return res.stdout
    except Exception as e:
        return f"Network check failed: {e}"

# --- 5. EXECUTION ---
if __name__ == "__main__":
    node_name = os.getenv('NODE_NAME', 'Homelab-Node-01')
    deps = Deps(server_name=node_name)
    
    query = "Perform a full system audit. Is the hardware and network okay?"
    result = agent.run_sync(query, deps=deps)
    print(result.output)