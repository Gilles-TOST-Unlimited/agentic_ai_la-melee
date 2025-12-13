import streamlit as st
import requests
import json
import os
from datetime import datetime
from mistralai import Mistral  # Updated import for v1.0+ SDK compatibility

# --- 1. CONFIGURATION & CONSTANTS ---
PAGE_TITLE = "Mistral Weather Agent"
PAGE_ICON = "🌤️"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# --- 2. TOOL DEFINITIONS & IMPLEMENTATIONS ---

def get_historical_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """
    Fetches historical weather data (temperature and humidity) for a specific location and date range.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: A JSON string containing daily mean temperature and humidity or an error message.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ["temperature_2m_mean", "relative_humidity_2m_mean"],
        "timezone": "auto"
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # Parse relevant data for a cleaner LLM context
        daily_data = data.get("daily", {})
        times = daily_data.get("time", [])
        temps = daily_data.get("temperature_2m_mean", [])
        humidities = daily_data.get("relative_humidity_2m_mean", [])

        results = []
        for t, temp, hum in zip(times, temps, humidities):
            results.append(f"Date: {t} | Temp: {temp}°C | Humidity: {hum}%")

        return "\n".join(results)

    except requests.exceptions.RequestException as e:
        return f"Error fetching weather data: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"


# Define the Tool Schema for Mistral
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_historical_weather",
            "description": "Get historical weather data (mean temp and humidity) for a location and date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Decimal latitude of the location"},
                    "longitude": {"type": "number", "description": "Decimal longitude of the location"},
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"}
                },
                "required": ["latitude", "longitude", "start_date", "end_date"]
            }
        }
    }
]

# Map function names to actual Python functions
available_functions = {
    "get_historical_weather": get_historical_weather
}


# --- 3. AGENT LOGIC (MCP PATTERN) ---

def run_agent_interaction(client, model, messages):
    """
    Core MCP Loop:
    1. Send user prompt to LLM.
    2. Check if LLM wants to use a tool.
    3. If yes, execute tool and report back to LLM.
    4. If no (or after tool use), return final response.
    """

    # -- Step 1: Initial Call --
    response = client.chat.complete(
        model=model,
        messages=messages,
        tools=tools_schema,
        tool_choice="auto"
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # -- Step 2: Check for Tool Calls --
    if tool_calls:
        # Add the assistant's request to call a tool to history
        messages.append(response_message)

        # Create a status container in UI to visualize "Thinking"
        with st.status("🤖 Agent is thinking & using tools...", expanded=True) as status:

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                st.write(f"🛠️ **Tool Call:** `{function_name}`")
                st.code(json.dumps(function_args, indent=2), language='json')

                # -- Step 3: Execute Tool --
                function_to_call = available_functions[function_name]
                function_response = function_to_call(**function_args)

                st.write(f"📉 **API Output:**")
                st.text(function_response)

                # Add tool result to message history
                messages.append({
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                    "tool_call_id": tool_call.id
                })

            status.update(label="✅ Tool processing complete!", state="complete", expanded=False)

        # -- Step 4: Final Response after Tool Execution --
        second_response = client.chat.complete(
            model=model,
            messages=messages
        )
        return second_response.choices[0].message.content

    # If no tool was called, return the initial text
    return response_message.content


# --- 4. USER INTERFACE (STREAMLIT) ---

def main():
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")

    # Custom CSS for "Modern/Minimalist" look
    st.markdown("""
        <style>
        .stChatMessage {
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 10px;
        }
        .stButton button {
            border-radius: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ Configuration")
        api_key = st.text_input("Mistral API Key", type="password", help="Enter your Mistral AI API Key")
        model_choice = st.selectbox("Model", ["mistral-large-latest", "mistral-small-latest"])
        st.markdown("---")
        st.caption("Capabilities:")
        st.markdown("- 🌡️ Temperature (Mean)\n- 💧 Humidity (Mean)\n- 📅 Historical Data")

        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    # --- Main Chat Interface ---
    st.title(f"{PAGE_ICON} {PAGE_TITLE}")
    st.caption("Ask about historical weather (e.g., 'What was the weather in Paris on Jan 1st 2023?')")

    # Initialize Chat History
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display History
    for message in st.session_state.messages:
        # We generally skip rendering 'tool' messages directly in the main chat flow to keep it clean,
        # or render them conditionally. Here we render User and Assistant roles.
        if isinstance(message, dict):  # Handle dict messages
            if message["role"] in ["user", "assistant"] and message.get("content"):
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        elif hasattr(message, "role"):  # Handle Mistral object messages
            if message.role in ["user", "assistant"] and message.content:
                with st.chat_message(message.role):
                    st.markdown(message.content)

    # --- Input Handling ---
    if prompt := st.chat_input("Ask a question..."):
        if not api_key:
            st.error("Please enter your Mistral API Key in the sidebar.")
            st.stop()

        # Add user message to state and UI
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Initialize Client
        client = Mistral(api_key=api_key)

        # Prepare messages for API (Filter out UI-specific keys if necessary)
        # We need to ensure the message history format is strictly compatible with Mistral SDK
        api_messages = []
        for msg in st.session_state.messages:
            if isinstance(msg, dict):
                api_messages.append(msg)
            else:
                api_messages.append(msg)

        # Generate Response
        with st.chat_message("assistant"):
            try:
                final_answer = run_agent_interaction(client, model_choice, api_messages)
                st.markdown(final_answer)

                # Append final answer to history as a dict (simple format)
                st.session_state.messages.append({"role": "assistant", "content": final_answer})

            except Exception as e:
                st.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()