import streamlit as st
import asyncio
import json
import os

# Mistral SDK
from mistralai import Mistral

# MCP SDK Components
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

# --- CONFIGURATION ---
PAGE_TITLE = "Mistral MCP Agent"
PAGE_ICON = "🌩️"
MCP_SERVER_URL = "http://localhost:8000/sse"  # The address of our local server


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

            # Insert this at the very start of the messages list construction
            import datetime
            current_date = datetime.date.today().strftime("%Y-%m-%d")

            # Build initial history
            messages = [{"role": "system",
                         "content": f"You are a helpful assistant. Today's date is {current_date}."}] + [
                           {"role": m["role"], "content": m["content"]}
                           for m in st.session_state.messages
                           if m["role"] != "tool"
                       ]
            #
            # # Build initial history
            # messages = [
            #     {"role": m["role"], "content": m["content"]}
            #     for m in st.session_state.messages
            #     if m["role"] != "tool"
            # ]

            # 4. First LLM Call (Thinking)
            response = await client.chat.complete_async(
                model=model,
                messages=messages,
                tools=mistral_tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 5. Check if LLM wants to use a tool
            if tool_calls:
                # --- CRITICAL FIX STARTS HERE ---
                # We MUST add the assistant's request to the history before adding the tool's result.
                # Without this, the conversation flow is broken (User -> Tool Result), causing the error.
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": tool_calls
                })
                # --- CRITICAL FIX ENDS HERE ---

                # Also update UI state (for display purposes)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    # We don't necessarily need to store tool_calls in UI state,
                    # but we needed it in the 'messages' list above.
                })

                with st.status(f"🔌 Connecting to remote MCP Server...", expanded=True) as status:

                    for tool_call in tool_calls:
                        func_name = tool_call.function.name
                        func_args = json.loads(tool_call.function.arguments)

                        st.write(f"📞 **Calling Remote Tool:** `{func_name}`")
                        st.code(json.dumps(func_args, indent=2), language='json')

                        # 6. EXECUTE ON SERVER
                        result = await session.call_tool(func_name, arguments=func_args)
                        tool_output = result.content[0].text

                        st.write(f"📡 **Received Data:**")
                        st.text(tool_output)

                        # Append tool result to history
                        messages.append({
                            "role": "tool",
                            "name": func_name,
                            "content": tool_output,
                            "tool_call_id": tool_call.id
                        })

                    status.update(label="✅ Remote execution successful", state="complete", expanded=False)

                # 7. Final LLM Call (Synthesis)
                final_response = await client.chat.complete_async(
                    model=model,
                    messages=messages  # Now contains: [User, Assistant(ToolCall), Tool(Result)]
                )
                return final_response.choices[0].message.content

            return response_message.content

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

    st.markdown("""<style>.stChatMessage { border-radius: 10px; padding: 10px; }</style>""", unsafe_allow_html=True)

    with st.sidebar:
        st.header("⚙️ Agent Settings")
        api_key = st.text_input("Mistral API Key", type="password")
        model_choice = st.selectbox("Model", ["mistral-large-latest", "mistral-small-latest"])
        st.info("Ensure `weather_server.py` is running on port 8000!")

    st.title(f"{PAGE_ICON} {PAGE_TITLE}")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        if msg.get("content"):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about weather..."):
        if not api_key:
            st.error("API Key required.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                final_answer = asyncio.run(run_agent_cycle(prompt, api_key, model_choice))
                st.markdown(final_answer)
                st.session_state.messages.append({"role": "assistant", "content": final_answer})
            except Exception as e:
                st.error(f"Connection Error: {e}")
                st.caption("Is the MCP Server running? (Try `python weather_server.py`)")


if __name__ == "__main__":
    main()