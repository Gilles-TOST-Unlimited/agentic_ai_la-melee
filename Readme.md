# Mistral Weather Agent (MCP Architecture)

This project demonstrates a modular AI Agent architecture using the **Model Context Protocol (MCP)**. It decouples the "Brain" (Mistral AI LLM) from the "Body" (Tools), allowing for scalable, cloud-ready deployment.

The application consists of two main components:
1.  **Weather Server (`weather_server.py`)**: A standalone MCP server providing historical weather data.
2.  **AI Client (`weather_client.py`)**: A Streamlit-based UI that connects to the server, discovers tools, and uses Mistral AI to answer natural language queries.

## 🏗️ Architecture

The system follows a client-server pattern where the LLM (Client) communicates with tools (Server) over a standardized protocol (SSE - Server-Sent Events).



### Core Components
* **LLM Provider**: Mistral AI (Models: `mistral-large`, `mistral-small`)
* **Protocol**: Model Context Protocol (MCP) using `fastmcp` and `mcp-python-sdk`.
* **Transport**: HTTP/SSE (Server-Sent Events) for real-time communication.
* **Frontend**: Streamlit for a chat-based user interface.
* **Data Source**: Open-Meteo Archive API.

## 📂 Project Structure

```text
.
├── weather_server.py    # The "Tool": MCP Server exposing weather functions
├── weather_client.py    # The "Brain": Streamlit UI & Mistral Agent Logic
├── requirements.txt     # Python dependencies
├── Dockerfile           # Configuration for cloud deployment (Render/AWS)
└── README.md            # Documentation