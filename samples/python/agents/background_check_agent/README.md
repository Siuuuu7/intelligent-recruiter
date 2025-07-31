# Background Check Agent with A2A Protocol

This sample demonstrates how to implement a background verification agent built on [Semantic Kernel](https://github.com/microsoft/semantic-kernel/) and exposed through the A2A protocol. It showcases:

- **Multi-turn interactions**: The agent may request clarifications about candidate information
- **Streaming responses**: Returns incremental verification statuses
- **Conversational memory**: Maintains context (by leveraging Semantic Kernel's ChatHistory)
- **Push notifications**: Uses webhook-based notifications for asynchronous updates
- **Background verification tools**: Uses specialized tools to verify universities, companies, and projects

```mermaid
sequenceDiagram
    participant Client as A2A Client
    participant Server as A2A Server
    participant BCA as BackgroundCheckAgent
    plugin Plugin as BackgroundCheckPlugin
    participant VU as verify_university tool
    participant VC as verify_company tool
    participant VP as verify_project tool

    Client->>Server: Send task (candidate resume/info)
    Server->>BCA: Forward verification query

    Note over BCA: Extract entities to verify
    par University Verification
        BCA->>VU: Verify "Harvard University"
        VU->>BCA: Return "VERIFIED"
    and Company Verification
        BCA->>VC: Verify "Google Inc"
        VC->>BCA: Return "VERIFIED"
    and Project Verification
        BCA->>VP: Verify "AI chatbot project"
        VP->>BCA: Return "PLAUSIBLE"
    end

    BCA->>Server: Aggregate verification results
    Server->>Client: Streaming: "Processing background checks..."
    Server->>Client: Streaming: "Verifying educational credentials..."
    Server->>Client: Streaming: "Checking employment history..."
    Server->>Client: Artifact: Complete verification report
    Server->>Client: Final status: "Background check completed."
```

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/)
- Valid OpenAI/Azure OpenAI credentials. See [here](https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/?tabs=csharp-AzureOpenAI%2Cpython-AzureOpenAI%2Cjava-AzureOpenAI&pivots=programming-language-python#creating-a-chat-completion-service) for more details about Semantic Kernel AI connectors.

## Setup & Running

1. **Navigate to the samples directory**:

```bash
cd samples/python/agents/background_check_agent
```

2. **Create an environment file (.env) with your API credentials:**

```bash
AZURE_OPENAI_TOKEN="your_azure_openai_api_key"
AZURE_OPENAI_ENDPOINT="your_azure_openai_endpoint"
```

3. **Set up the Python Environment**:

> Note: pin the Python version to your desired version (3.10+)

```bash
uv python pin 3.12
uv venv
source .venv/bin/activate
```

4. **Run the agent**:

Choose one of the following options:

> Make sure you run `uv run .` from the following directory: `samples/python/agents/background_check_agent`

```bash
# Basic run on default port 10019
uv run .
```
or

```bash
# On custom host/port
uv run . --host 0.0.0.0 --port 8080
```

5. **In a separate terminal, run the A2A client:**

> Make sure you run `uv run .` from the following directory: `samples/python/hosts/cli`

```bash
cd samples/python/hosts/cli
uv run . --agent http://localhost:10019
```

## Verification Capabilities

The agent can verify:
- **Universities**: Checks against a database of legitimate accredited institutions
- **Companies**: Validates employment claims against known organizations
- **Projects**: Assesses plausibility of claimed achievements and flags suspicious items

## Limitations

- Only text-based input/output for now
- Verification tools use dummy implementations for demonstration
- Session-based memory is ephemeral (in-memory)

## Example Endpoints

You can POST A2A requests to http://localhost:10019 with JSON-RPC specifying tasks/send or tasks/sendSubscribe. Here is a synchronous snippet:

### Request:

POST http://localhost:10019
Content-Type: application/json

```json
{
  "jsonrpc": "2.0",
  "id": 33,
  "method": "tasks/send",
  "params": {
    "id": "3",
    "sessionId": "1aab49f1e85c499da48c2124f4ceee4d",
    "acceptedOutputModes": ["text"],
    "message": {
      "role": "user",
      "parts": [
        { "type": "text", "text": "Please verify this candidate: John Smith, graduated from MIT, worked at Google, claims to have invented a revolutionary AI algorithm." }
      ]
    }
  }
}
```

### Response:

```json
{
  "jsonrpc": "2.0",
  "id": 33,
  "result": {
    "id": "3",
    "status": {
      "state": "completed",
      "timestamp": "2025-04-01T16:53:29.301828"
    },
    "artifacts": [
      {
        "parts": [
          {
            "type": "text",
            "text": "Background Check Results:\n- University: MIT - VERIFIED\n- Company: Google - VERIFIED\n- Project: Revolutionary AI algorithm - NEEDS FURTHER REVIEW\n\nOverall Status: PARTIALLY VERIFIED"
          }
        ],
        "index": 0
      }
    ],
    "history": []
  }
}
```

For more details, see [A2A Protocol Documentation](https://google.github.io/A2A/#/documentation) and [Semantic Kernel Docs](https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide?pivots=programming-language-python).