# Mistral Weather Agent (MCP Architecture)

This project demonstrates a modular AI Agent architecture using the **Model Context Protocol (MCP)**. It decouples the "Brain" (Mistral AI via Streamlit) from the "Body" (Weather Tool Server), enabling robust and scalable cloud deployment.

The system consists of two distinct entities:
1.  **Weather Server (`weather_server.py`)**: A standard MCP server hosted via **Starlette** and **Uvicorn**, exposing historical weather data.
2.  **AI Client (`weather_client.py`)**: A Streamlit user interface that connects to the server, discovers available tools, and uses Mistral AI to answer questions.

## 🏗️ Architecture

The system follows an asynchronous Client-Server model:

* **Server**: Uses `Starlette` to create a standard ASGI application compatible with Cloud platforms (Render, AWS, etc.).
* **Transport**: Communication via HTTP/SSE (Server-Sent Events).
* **Client**: Streamlit connects to the remote (or local) URL and orchestrates the AI reasoning.

## 📂 Project Structure

```text
.
├── weather_server.py    # MCP Server (Weather Logic + Starlette App)
├── weather_client.py    # Streamlit Client (Chat Interface + Agent Logic)
├── requirements.txt     # Python Dependencies
├── Dockerfile           # Configuration for Cloud Deployment (Render)
└── README.md            # Documentation
````

## 🚀 Installation

### Prerequisites

  * Python 3.10+
  * A valid [Mistral AI API Key](https://console.mistral.ai/)

### 1\. Install Dependencies

Clone the repository and install the required packages:

```bash
git clone [https://github.com/your-username/mistral-weather-mcp.git](https://github.com/your-username/mistral-weather-mcp.git)
cd mistral-weather-mcp
pip install -r requirements.txt
```

**Content of `requirements.txt`:**

```text
mcp
mistralai>=1.0.0
requests
uvicorn
starlette
```

## 💻 Local Execution

To test on your machine, run the Server and Client in two separate terminals.

### Terminal 1: Start the MCP Server

We use `uvicorn` to serve the Starlette application defined in the script.

```bash
uvicorn weather_server:starlette_app --reload --port 8000
```

*The server will listen on `http://127.0.0.1:8000`.*

### Terminal 2: Start the Streamlit Client

```bash
streamlit run weather_client.py
```

  * Open your browser to `http://localhost:8501`.
  * Enter your Mistral API Key.
  * Ensure the `MCP_SERVER_URL` variable in `weather_client.py` points to `http://localhost:8000/sse`.

## ☁️ Cloud Deployment (Render.com)

The project is configured for Docker deployment.

### 1\. Docker Configuration

The `Dockerfile` uses a specific command to expose the application on all interfaces (`0.0.0.0`), which is mandatory for cloud providers.

```dockerfile
# Dockerfile snippet
CMD ["uvicorn", "weather_server:starlette_app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2\. Deployment Steps

1.  Push your code to GitHub.
2.  Create a new **Web Service** on [Render](https://render.com).
3.  Connect your GitHub repository.
4.  Select the **Docker** environment.
5.  Once deployed, copy the URL (e.g., `https://my-weather-app.onrender.com`).

### 3\. Connect the Client

Update the URL in `weather_client.py` to point to the cloud:

```python
# weather_client.py
MCP_SERVER_URL = "[https://my-weather-app.onrender.com/sse](https://my-weather-app.onrender.com/sse)"
```

## 🧠 Technical Explanation

### Why Starlette?

Instead of using the high-level `FastMCP` abstraction (which can hide critical implementation details for the cloud), we explicitly define a **Starlette** application.

  * This creates a standard **ASGI** app (`starlette_app`).
  * It allows `uvicorn` to find and execute the server without missing attribute errors.

### Low-Level ASGI Handlers

To avoid conflicts between Starlette and the MCP SDK, routes are defined as raw ASGI handlers:

```python
# Direct network stream management (scope, receive, send)
async def handle_sse(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(...)
```

This ensures the MCP SDK can write responses (202 Accepted, SSE stream) directly, bypassing Starlette's response validation and resolving the `TypeError: 'NoneType' object is not callable` error.

## 🤝 Contribution

Pull Requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/)


