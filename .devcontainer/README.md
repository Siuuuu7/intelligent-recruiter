# A2A Development Container

This dev container provides a complete development environment for the Agent2Agent (A2A) project with all necessary dependencies pre-installed.

## What's included

- **Python 3.13** with `uv` package manager
- **Node.js 20** with `pnpm` package manager  
- **VS Code extensions** for Python, TypeScript, and development tools
- **Pre-configured environment** with all project dependencies
- **Helpful aliases** for common development tasks

## Quick Start

1. **Open in Dev Container**
   - Install the "Dev Containers" VS Code extension
   - Open this project in VS Code
   - Click "Reopen in Container" when prompted

2. **Configure Environment**
   - Update `.env` file with your API keys:
     ```bash
     GOOGLE_API_KEY=your_actual_api_key
     AZURE_OPENAI_ENDPOINT=your_azure_endpoint
     AZURE_OPENAI_TOKEN=your_azure_token
     ```

3. **Start Development**
   ```bash
   a2a-ui      # Start the UI server
   a2a-info    # Check environment info
   ```

## Available Commands

| Command | Description |
|---------|-------------|
| `a2a-ui` | Start the A2A UI server |
| `a2a-agents` | Navigate to Python agents directory |
| `a2a-js` | Navigate to JavaScript samples |
| `a2a-lint` | Run Python linting |
| `a2a-format` | Format Python code |
| `a2a-info` | Show environment information |

## Ports

The following ports are automatically forwarded:

- **12000** - A2A UI Server
- **41241** - Agent Server  
- **8000** - FastAPI default
- **3000** - Common dev server

## Environment Variables

Key environment variables in `.env`:

- `DEBUG_MODE` - Set to "true" for verbose logging
- `GOOGLE_API_KEY` - Your Google AI API key
- `AZURE_OPENAI_*` - Azure OpenAI configuration for agent routing

## Troubleshooting

**Container won't start?**
- Check Docker is running
- Try rebuilding: Command Palette → "Dev Containers: Rebuild Container"

**Dependencies missing?**
- The post-create script installs everything automatically
- If issues persist, run: `cd /workspaces/intelligent-recruiter && .devcontainer/post-create.sh`

**Port conflicts?**
- Modify `forwardPorts` in `devcontainer.json` if needed