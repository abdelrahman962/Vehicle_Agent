import json
import re
import time
import uuid

import requests
import streamlit as st
from langchain_core.runnables import RunnableConfig

from pitstrack_api.agent import agent


API_BASE_URL = "http://127.0.0.1:8000"

# Matches "another 5 vehicles" / "next 5" / "show me more vehicles", but not
# "vehicles with speed more than 50" (a real filter condition, not a
# pagination request).
_MORE_VEHICLES_PATTERN = re.compile(
    r"\b(another|next)\b|\bmore\b(?!\s+than)",
    re.IGNORECASE,
)


st.set_page_config(page_title="Vehicle Agent")
st.title("Vehicle Agent")


def is_tool_error(message) -> bool:
    if type(message).__name__ != "ToolMessage":
        return False

    if getattr(message, "status", None) == "error":
        return True

    content = message.content

    return isinstance(content, str) and content.startswith("Error invoking tool")


def get_all_tool_results(messages):
    results = []

    for message in messages:
        if type(message).__name__ != "ToolMessage":
            continue

        if is_tool_error(message):
            continue

        if not isinstance(message.content, str):
            continue

        try:
            data = json.loads(message.content)
        except json.JSONDecodeError:
            continue

        results.append((getattr(message, "name", None), data))

    return results


def _find_matching_group_key(groups, query_text):
    if not query_text:
        return None

    query_lower = query_text.lower()

    matches = [
        key
        for key in groups
        if key != "(unavailable)"
        and len(key.strip()) > 2
        and key.strip().lower() in query_lower
    ]

    return matches[0] if len(matches) == 1 else None


def render_single(tool_name, tool_data, query_text=""):
    if tool_name:
        st.caption(f"via `{tool_name}`")

    if "vehicle" in tool_data or "found" in tool_data:
        if not tool_data.get("found"):
            st.write("No matching vehicle found.")
            return

        st.dataframe([tool_data["vehicle"]], hide_index=True)
        return

    if "groups" in tool_data:
        groups = tool_data["groups"]
        is_detailed = any(isinstance(v, dict) for v in groups.values())

        matched_key = _find_matching_group_key(groups, query_text)

        if matched_key is not None:
            group = groups[matched_key]

            if is_detailed:
                total = group.get("total", 0)
                vehicles = group.get("vehicles", [])
                st.write(
                    f"`{tool_data.get('field')} = {matched_key}`: {total} vehicle(s):"
                )
                if vehicles:
                    st.dataframe(vehicles, hide_index=True)
                else:
                    st.write("No vehicle details available for this group.")
            else:
                st.write(f"`{tool_data.get('field')} = {matched_key}`: {group} vehicle(s).")
            return

        st.write(f"Grouped by `{tool_data.get('field')}` ({tool_data.get('total', 0)} vehicle(s)):")

        if not is_detailed:
            st.bar_chart(groups)
            return

        for key, group in groups.items():
            with st.expander(f"{key} ({group.get('total', 0)} vehicle(s))"):
                vehicles = group.get("vehicles", [])
                if vehicles:
                    st.dataframe(vehicles, hide_index=True)
                else:
                    st.write("No vehicles in this group.")
        return

    records = tool_data.get("records")

    if records is not None:
        if not records:
            st.write("No vehicles found.")
            return

        if tool_data.get("sort_field_unavailable"):
            st.warning(tool_data["sort_field_unavailable"])

        st.write(f"Showing {len(records)} of {tool_data.get('count', len(records))} matching vehicle(s):")
        st.dataframe(records, hide_index=True)
        return

    if "count" in tool_data:
        st.write(f"Total vehicles: {tool_data['count']}")
        return

    st.json(tool_data)


def render_result(tool_results, answer_text, query_text=""):
    if not tool_results:
        st.write(answer_text)
        return

    for tool_name, tool_data in tool_results:
        render_single(tool_name, tool_data, query_text)


def _extract_ids(records):
    return [row["id"] for row in records if isinstance(row, dict) and "id" in row]


def _extract_requested_limit(text, default):
    match = re.search(r"\d+", text)
    return int(match.group()) if match else default


def _fetch_more_vehicles(exclude_ids, limit):
    params = {
        "filter_field": "id",
        "filter_operator": "not in",
        "filter_value": ",".join(str(i) for i in exclude_ids),
        "limit": limit,
    }
    response = requests.get(f"{API_BASE_URL}/vehicles", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "graph_message_count" not in st.session_state:
    st.session_state.graph_message_count = 0

if "shown_vehicle_ids" not in st.session_state:
    st.session_state.shown_vehicle_ids = set()

if "last_vehicles_limit" not in st.session_state:
    st.session_state.last_vehicles_limit = 5


config: RunnableConfig = {
    "configurable": {
        "thread_id": st.session_state.thread_id,
    }
}


for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            prior_user_text = ""
            if idx > 0 and st.session_state.messages[idx - 1]["role"] == "user":
                prior_user_text = st.session_state.messages[idx - 1]["content"]

            render_result(
                message.get("tool_results", []), message["content"], prior_user_text
            )

            if "elapsed" in message:
                st.caption(f"⏱ {message['elapsed']:.2f}s")
        else:
            st.write(message["content"])


user_input = st.chat_input("Ask about your vehicles...")

if user_input:
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.write(user_input)

    start_time = time.perf_counter()

    is_more_request = bool(
        _MORE_VEHICLES_PATTERN.search(user_input)
    ) and st.session_state.shown_vehicle_ids

    if is_more_request:
        limit = _extract_requested_limit(user_input, st.session_state.last_vehicles_limit)

        print("\n" + "=" * 60)
        print("DEBUG: PAGINATION SHORT-CIRCUIT for query:", user_input)
        print("Excluding ids:", st.session_state.shown_vehicle_ids)
        print("=" * 60)

        tool_data = _fetch_more_vehicles(st.session_state.shown_vehicle_ids, limit)
        tool_results = [("get_vehicles", tool_data)]
        answer = ""
    else:
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ]
            },
            config=config,
        )

        new_messages = result["messages"][st.session_state.graph_message_count :]
        st.session_state.graph_message_count = len(result["messages"])

        print("\n" + "=" * 60)
        print("DEBUG: AGENT EXECUTION for query:", user_input)
        print("=" * 60)

        for i, message in enumerate(result["messages"]):
            print(f"\n--- MESSAGE {i} ---")
            print("TYPE:", type(message).__name__)

            if getattr(message, "tool_calls", None):
                print("TOOL CALLS:", message.tool_calls)

            if type(message).__name__ == "ToolMessage":
                print("TOOL NAME:", getattr(message, "name", None))
                print("TOOL CONTENT:", message.content)

            elif isinstance(message.content, str) and message.content:
                print("CONTENT:", message.content)

        if new_messages and is_tool_error(new_messages[-1]):
            answer = "Sorry, I had trouble processing that request. Could you rephrase it?"
        else:
            answer = new_messages[-1].content if new_messages else ""

        tool_results = get_all_tool_results(new_messages)

    elapsed = time.perf_counter() - start_time
    print(f"\nTOTAL TIME: {elapsed:.3f}s")

    for _, tool_data in tool_results:
        records = tool_data.get("records") if isinstance(tool_data, dict) else None
        if records:
            st.session_state.shown_vehicle_ids.update(_extract_ids(records))
            st.session_state.last_vehicles_limit = len(records)

    with st.chat_message("assistant"):
        render_result(tool_results, answer, user_input)
        st.caption(f"⏱ {elapsed:.2f}s")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "tool_results": tool_results,
            "elapsed": elapsed,
        }
    )
