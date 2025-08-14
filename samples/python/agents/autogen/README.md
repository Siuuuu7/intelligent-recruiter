# AutoGen Candidate Evaluation Agent

A specialized multi-agent system for candidate evaluation built with AutoGen framework and the A2A Python SDK. This agent uses multiple specialized agents (Tech Rater, Inclusion Rater, Reporter) to provide comprehensive candidate assessment for AI Scientist positions at SAP.

## Prerequisites

- Python 3.12 or higher
- `AZURE_OPENAI_TOKEN` environment variable set
- `AZURE_OPENAI_ENDPOINT` environment variable set
- A2A Python SDK (`a2a-sdk`)

## Setup

```bash
# Using uv (recommended)
uv sync
```

## Environment Variables

Create a `.env` file with:

```bash
AZURE_OPENAI_TOKEN="your_azure_openai_api_key"
AZURE_OPENAI_ENDPOINT="your_azure_openai_endpoint"
```

## Running

```bash
uv run .
```

The agent will start on port 10018 by default.

## Agent Architecture

This multi-agent system consists of:

- **Tech Rater**: Evaluates technical expertise, programming skills, and domain knowledge
- **Inclusion Rater**: Assesses diversity background and inclusion contributions  
- **Reporter**: Synthesizes evaluations from other agents into a comprehensive final report

## Files

- `agents/autogen/__init__.py`: Package initialization
- `agents/autogen/__main__.py`: Entry point and server setup
- `agents/autogen/agent.py`: Core AutoGen multi-agent logic
- `agents/autogen/task_manager.py`: A2A task management integration
- `pyproject.toml`: Dependencies
- `README.md`: Usage guide

## Example Usage

Send candidate information for evaluation:

```
"Evaluate this candidate: John Smith; 5 years as Software Engineer at Google, PhD in Computer Science from MIT, active in diversity initiatives, fluent in Python and JavaScript."
```

The system will provide ratings for technical skills, diversity background, and an overall recommendation.

This project is part of the AutoGen agent samples and follows the same licensing terms.

## Disclaimer

Important: The sample code provided is for demonstration purposes and illustrates the mechanics of the Agent-to-Agent (A2A) protocol. When building production applications, it is critical to treat any agent operating outside of your direct control as a potentially untrusted entity.

All data received from an external agent—including but not limited to its AgentCard, messages, artifacts, and task statuses—should be handled as untrusted input. For example, a malicious agent could provide an AgentCard containing crafted data in its fields (e.g., description, name, skills.description). If this data is used without sanitization to construct prompts for a Large Language Model (LLM), it could expose your application to prompt injection attacks. Failure to properly validate and sanitize this data before use can introduce security vulnerabilities into your application.

Developers are responsible for implementing appropriate security measures, such as input validation and secure handling of credentials to protect their systems and users.