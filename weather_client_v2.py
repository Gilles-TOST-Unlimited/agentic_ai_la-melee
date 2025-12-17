import streamlit as st
import asyncio
import json
import base64
import datetime
import os

# Mistral SDK
from mistralai import Mistral

# MCP SDK Components
from mcp import ClientSession
from mcp.client.sse import sse_client

# --- CONFIGURATION ---
PAGE_TITLE = "Mistral MCP Agent"
PAGE_ICON = "🌩️"

# CLOUD URL (Make sure this matches your deployed server)
# MCP_SERVER_URL = "https://agentic-ai-la-melee.onrender.com/sse"
MCP_SERVER_URL = "http://localhost:8000/sse"


# --- HELPER: LOAD API KEY ---
def load_api_key_from_file():
    """
    Attempts to read 'mistral.txt' from the parent directory of this script.
    Returns the key if found, else an empty string.
    """
    try:
        # Get the absolute path of the directory containing this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct path to ../mistral.txt
        file_path = os.path.join(current_dir, "..", "mistral.txt")

        # Check if file exists and read it
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                key = f.read().strip()
                if key:
                    return key
    except Exception:
        pass  # Fail silently if file doesn't exist or permissions error
    return ""


# --- HELPER: CONVERT MCP TOOLS TO MISTRAL TOOLS ---
def mcp_tool_to_mistral_schema(mcp_tool):
    """
    Converts an MCP Tool definition into a Mistral-compatible function schema.
    """
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.inputSchema
        }
    }


# --- CORE AGENT LOGIC (ASYNC) ---
async def run_agent_cycle(user_query, api_key, model):
    """
    Runs the agent cycle and returns a tuple: (final_text_response, list_of_base64_images)
    """
    # 1. Connect to the MCP Server
    async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            # 2. Initialize Session & Discover Tools
            await session.initialize()
            tools_result = await session.list_tools()
            available_tools = tools_result.tools
            mistral_tools = [mcp_tool_to_mistral_schema(t) for t in available_tools]

            # 3. Setup Mistral Client
            client = Mistral(api_key=api_key)

            # Insert System Prompt with Date
            current_date = datetime.date.today().strftime("%Y-%m-%d")

            # Rebuild history for LLM
            messages = [{"role": "system",
                         "content": f"You are a helpful assistant. Today's date is {current_date}. If a user asks for a chart or graph, use the 'get_weather_visualization' tool."}]

            # Append chat history (excluding previous tool raw outputs)
            for m in st.session_state.messages:
                if m["role"] != "tool":
                    messages.append({"role": m["role"], "content": m["content"]})

            # 4. First LLM Call (Thinking)
            response = await client.chat.complete_async(
                model=model,
                messages=messages,
                tools=mistral_tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # List to store any images generated during this cycle
            generated_images = []

            # 5. Check if LLM wants to use a tool
            if tool_calls:
                # Add assistant's intent to history
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": tool_calls
                })

                # Update UI state (Assistant thinking)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                })

                with st.status(f"🔌 Connecting to remote MCP Server...", expanded=True) as status:

                    for tool_call in tool_calls:
                        func_name = tool_call.function.name
                        func_args = json.loads(tool_call.function.arguments)

                        st.write(f"📞 **Calling Remote Tool:** `{func_name}`")
                        st.code(json.dumps(func_args, indent=2), language='json')

                        # 6. EXECUTE ON SERVER
                        result = await session.call_tool(func_name, arguments=func_args)

                        # --- HANDLING MIXED CONTENT (Text vs Image) ---
                        tool_response_text = ""

                        for content in result.content:
                            if content.type == "text":
                                st.write(f"📡 **Received Text Data:**")
                                st.text(content.text)
                                tool_response_text += content.text

                            elif content.type == "image":
                                st.write(f"🖼️ **Received Chart:**")

                                # 1. Show immediately in the status container
                                image_data = base64.b64decode(content.data)
                                # FIX 1: Replaced use_column_width with use_container_width
                                st.image(image_data, caption="Weather Visualization", width='stretch')

                                # 2. Save base64 string to list so we can return it
                                generated_images.append(content.data)

                                # We tell the LLM that an image was generated
                                tool_response_text += "[Image Generated Successfully]"

                        # Append tool result to history for the final LLM synthesis
                        messages.append({
                            "role": "tool",
                            "name": func_name,
                            "content": tool_response_text,
                            "tool_call_id": tool_call.id
                        })

                    status.update(label="✅ Remote execution successful", state="complete", expanded=False)

                # 7. Final LLM Call (Synthesis)
                final_response = await client.chat.complete_async(
                    model=model,
                    messages=messages
                )
                return final_response.choices[0].message.content, generated_images

            # If no tool called, return just content and empty image list
            return response_message.content, []


# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

    st.markdown("""<style>.stChatMessage { border-radius: 10px; padding: 10px; }</style>""", unsafe_allow_html=True)

    # Load API Key from file if available
    default_api_key = load_api_key_from_file()

    with st.sidebar:
        st.header("⚙️ Agent Settings")
        # Use the loaded key as the default value
        api_key = st.text_input("Mistral API Key", value=default_api_key, type="password")
        model_choice = st.selectbox("Model", ["mistral-large-latest", "mistral-small-latest"])
        st.info("Server: " + MCP_SERVER_URL)

    st.title(f"{PAGE_ICON} {PAGE_TITLE}")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            # 1. Show Text
            if msg.get("content"):
                st.markdown(msg["content"])

            # 2. Show Images (if any exist for this message)
            if msg.get("images"):
                for img_b64 in msg["images"]:
                    # FIX 2: Replaced use_column_width with use_container_width
                    st.image(base64.b64decode(img_b64), caption="Generated Chart", width='stretch')

    # Input Handler
    if prompt := st.chat_input("Ask about weather (e.g. 'Chart for Paris last week')..."):
        if not api_key:
            st.error("API Key required.")
            st.stop()

        # Add User Message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate Assistant Response
        with st.chat_message("assistant"):
            try:
                # Run cycle and unpack result (text + images)
                final_answer, images = asyncio.run(run_agent_cycle(prompt, api_key, model_choice))

                # Show Text
                st.markdown(final_answer)

                # Show Images (if new ones were generated)
                if images:
                    for img_b64 in images:
                        # FIX 3: Replaced use_column_width with use_container_width
                        st.image(base64.b64decode(img_b64), caption="Generated Chart", width='stretch')

                # Save to History (Text + Images)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": final_answer,
                    "images": images  # Store images here for persistence
                })

            except Exception as e:
                st.error(f"Connection Error: {e}")
                st.caption("Check your server URL and internet connection.")


if __name__ == "__main__":
    main()