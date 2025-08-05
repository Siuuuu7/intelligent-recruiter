#!/bin/bash

# Post-create script for A2A development environment
set -e

echo "🚀 Setting up A2A development environment..."

# Set ownership of the workspace to vscode user
sudo chown -R vscode:vscode /workspaces/a2a-1

# Create Python virtual environment and install dependencies
echo "📦 Installing Python dependencies..."
cd /workspaces/a2a-1

# Install Python samples dependencies
echo "Installing Python samples..."
cd samples/python
uv sync
cd ../..

# Install UI dependencies
echo "Installing UI dependencies..."
cd demo/ui
uv sync
cd ../..

# Install JavaScript dependencies
echo "Installing JavaScript dependencies..."
cd samples/js
pnpm install
cd ../..

# Create .env file template if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env template..."
    cat > .env << 'EOF'
# Google AI Configuration
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# Azure OpenAI Configuration (for agent routing)
AZURE_OPENAI_ENDPOINT=your_azure_endpoint_here
AZURE_OPENAI_TOKEN=your_azure_token_here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o

# Debug Mode (set to "true" to enable verbose logging)
DEBUG_MODE=false

# Server Configuration
A2A_UI_HOST=0.0.0.0
A2A_UI_PORT=12000
A2A_HOST=ADK

# Agent URLs (add your agent URLs here)
# AGENT_URL_1=http://localhost:41241
EOF
    echo "✅ Created .env template. Please update with your actual values."
fi

# Set up git hooks (if any)
echo "🔧 Setting up git hooks..."
# Add any git hooks setup here if needed

# Make scripts executable
find . -name "*.sh" -exec chmod +x {} \;

# Create helpful aliases
echo "🔗 Setting up helpful aliases..."
cat >> ~/.bashrc << 'EOF'

# A2A Development Aliases
alias a2a-ui='cd /workspaces/a2a-1/demo/ui && uv run python main.py'
alias a2a-agents='cd /workspaces/a2a-1/samples/python'
alias a2a-js='cd /workspaces/a2a-1/samples/js'
alias a2a-test='cd /workspaces/a2a-1 && python -m pytest'
alias a2a-lint='cd /workspaces/a2a-1/demo/ui && uv run ruff check .'
alias a2a-format='cd /workspaces/a2a-1/demo/ui && uv run ruff format .'

# Useful environment info
alias a2a-info='echo "A2A Development Environment Info:" && echo "Python: $(python --version)" && echo "Node.js: $(node --version)" && echo "pnpm: $(pnpm --version)" && echo "uv: $(uv --version)"'
EOF

echo "🎉 A2A development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env file with your API keys and configuration"
echo "2. Run 'a2a-ui' to start the UI server"
echo "3. Run 'a2a-info' to see environment information"
echo ""
echo "Available commands:"
echo "  a2a-ui     - Start the UI server"
echo "  a2a-agents - Navigate to Python agents directory"
echo "  a2a-js     - Navigate to JavaScript samples directory"
echo "  a2a-lint   - Run Python linting"
echo "  a2a-format - Format Python code"
echo "  a2a-info   - Show environment information"