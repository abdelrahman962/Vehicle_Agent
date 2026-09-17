from pathlib import Path

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from app.agent.memory import get_checkpointer
from pitstrack_api.langchain_tools import (
    get_vehicle_counts_by_field,
    get_vehicle_details,
    get_vehicles,
    get_vehicles_count,
    get_vehicles_grouped_by_field,
)


SYSTEM_PROMPT = (
    Path(__file__).resolve().parent / "agent_instructions.md"
).read_text(encoding="utf-8")


model = ChatOllama(
    model="qwen3:1.7b",
    temperature=0,
    reasoning=False,
)


checkpointer_context = get_checkpointer()
checkpointer = checkpointer_context.__enter__()


agent = create_agent(
    model=model,
    tools=[
        get_vehicles,
        get_vehicles_count,
        get_vehicle_details,
        get_vehicle_counts_by_field,
        get_vehicles_grouped_by_field,
    ],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    interrupt_after=["tools"],
)
