import json
import uuid
from typing import List

from google.genai import types
import base64

from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
from common.client import A2ACardResolver
from common.types import (
    AgentCard,
    Message,
    TaskState,
    Task,
    TaskSendParams,
    TextPart,
    DataPart,
    Part,
)


class HostAgent:
    """The host agent.

    This is the agent responsible for choosing which remote agents to send
    tasks to and coordinate their work.
    """

    def __init__(
        self,
        remote_agent_addresses: List[str],
        task_callback: TaskUpdateCallback | None = None,
    ):
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}

        for address in remote_agent_addresses:
            if isinstance(address, AgentCard):
                print(f"[DEBUG] Received AgentCard directly: {address.url}")
                card = address  # Use it directly (don't resolve again)
            else:
                print(f"[DEBUG] Trying to connect to agent URL: {address}")
                try:
                    card_resolver = A2ACardResolver(address)
                    card = card_resolver.get_agent_card()
                except Exception as e:
                    print(f"[WARN] Skipping agent {address} because of error: {e}")
                    continue  # SKIP this broken agent, don't crash

            remote_connection = RemoteAgentConnections(card)
            self.remote_agent_connections[card.name] = remote_connection
            self.cards[card.name] = card

        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def register_agent_card(self, card: AgentCard):
        remote_connection = RemoteAgentConnections(card)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card
        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def create_agent(self) -> Agent:
        return Agent(
            model="gemini-2.0-flash-001",
            name="host_agent",
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            description=(
                "This agent orchestrates the decomposition of the user request into"
                " tasks that can be performed by the child agents."
            ),
            tools=[
                self.list_remote_agents,
                self.send_task,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        current_agent = self.check_state(context)
        state = context.state

        # Include file context if available
        file_context = ""
        if "file_context" in state:
            file_context = f"\n\nFile Context: {state['file_context']}"

        return f"""You are an expert delegator that coordinates candidate evaluation workflows by delegating tasks to appropriate remote agents based on their capabilities.

Discovery:
- Use `list_remote_agents` to discover available remote agents and their specific capabilities
- Each agent has different specializations - examine their descriptions to match user requests appropriately

Execution:
- For actionable tasks, use `send_task` to delegate tasks to the most suitable remote agent
- Always include the specific agent name when responding to the user
- Base your delegation decisions on the agent capabilities, not assumptions

File Processing:
- Uploaded files (PDF, DOCX, TXT) are processed by the UI server before reaching agents
- Extracted text content is embedded directly into the user's message
- Agents receive the complete file content as part of the text input - no separate file handling required
- When file content is present in the message, use this context for informed delegation

Task Management:
- Use `check_pending_task_states` to monitor the status of ongoing tasks
- If there is an active agent session, continue sending requests to that agent
- Focus on the most recent parts of the conversation for context

Guidelines:
- Always rely on available tools - do not make up responses
- If uncertain about which agent to use, ask the user for clarification
- Provide clear context about what information has been extracted from uploaded files

Available Agents:
{self.agents}

Current Active Agent: {current_agent['active_agent']}{file_context}
"""

    def check_state(self, context: ReadonlyContext):
        state = context.state
        if (
            "session_id" in state
            and "session_active" in state
            and state["session_active"]
            and "agent" in state
        ):
            return {"active_agent": f'{state["agent"]}'}
        return {"active_agent": "None"}

    def before_model_callback(self, callback_context: CallbackContext, llm_request):
        state = callback_context.state
        if "session_active" not in state or not state["session_active"]:
            if "session_id" not in state:
                state["session_id"] = str(uuid.uuid4())
            state["session_active"] = True

        # Add context about uploaded files if present
        if "input_message_metadata" in state and state["input_message_metadata"]:
            metadata = state["input_message_metadata"]
            if "file_path" in metadata:
                # Inject file context into the conversation
                file_path = metadata["file_path"]
                filename = file_path.split("/")[-1] if "/" in file_path else file_path
                state["file_context"] = (
                    f"Note: User has uploaded a file '{filename}' that needs to be processed."
                )
                print(f"[DEBUG] Host Agent: Added file context to state: {filename}")

    def list_remote_agents(self):
        """List the available remote agents you can use to delegate the task."""
        if not self.remote_agent_connections:
            return []

        remote_agent_info = []
        for card in self.cards.values():
            remote_agent_info.append(
                {"name": card.name, "description": card.description}
            )
        return remote_agent_info

    async def send_task(self, agent_name: str, message: str, tool_context: ToolContext):
        """Sends a task either streaming (if supported) or non-streaming.

        This will send a message to the remote agent named agent_name.

        Args:
          agent_name: The name of the agent to send the task to.
          message: The message to send to the agent for the task.
          tool_context: The tool context this method runs in.

        Yields:
          A dictionary of JSON data.
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        state = tool_context.state
        state["agent"] = agent_name
        card = self.cards[agent_name]
        client = self.remote_agent_connections[agent_name]
        if not client:
            raise ValueError(f"Client not available for {agent_name}")
        if "task_id" in state:
            taskId = state["task_id"]
        else:
            taskId = str(uuid.uuid4())
        sessionId = state["session_id"]
        task: Task
        messageId = ""
        metadata = {}
        if "input_message_metadata" in state:
            print(
                f"[DEBUG] Multiagent Host: input_message_metadata keys: {list(state['input_message_metadata'].keys())}"
            )
            print(
                f"[DEBUG] Multiagent Host: input_message_metadata content: {state['input_message_metadata']}"
            )
            metadata.update(**state["input_message_metadata"])
            if "message_id" in state["input_message_metadata"]:
                messageId = state["input_message_metadata"]["message_id"]
        if not messageId:
            messageId = str(uuid.uuid4())
        metadata.update(**{"conversation_id": sessionId, "message_id": messageId})

        # Forward file path information if available
        if (
            "input_message_metadata" in state
            and "file_path" in state["input_message_metadata"]
        ):
            metadata["file_path"] = state["input_message_metadata"]["file_path"]
            print(
                f"[DEBUG] Multiagent Host: Forwarding file_path to {agent_name}: {metadata['file_path']}"
            )
        else:
            print(
                f"[DEBUG] Multiagent Host: No file_path found in input_message_metadata for {agent_name}"
            )

        print(
            f"[DEBUG] Multiagent Host: Final metadata being sent to {agent_name}: {metadata}"
        )

        # Create TaskSendParams metadata that includes file_path if available
        task_metadata = {"conversation_id": sessionId}
        if "file_path" in metadata:
            task_metadata["file_path"] = metadata["file_path"]
            print(
                f"[DEBUG] Multiagent Host: Added file_path to TaskSendParams metadata: {metadata['file_path']}"
            )

        request: TaskSendParams = TaskSendParams(
            id=taskId,
            sessionId=sessionId,
            message=Message(
                role="user",
                parts=[TextPart(text=message)],
                metadata=metadata,
            ),
            acceptedOutputModes=[
                "text",
                "text/plain",
                "image/png",
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ],
            # pushNotification=None,
            metadata=task_metadata,
        )
        task = await client.send_task(request, self.task_callback)

        # Handle case where task is None (can happen with streaming tasks)
        if task is None:
            print(
                f"[WARN] Task returned None for agent {agent_name}, assuming completion"
            )
            state["session_active"] = False
            return f"Task completed but no final status received from {agent_name}"

        # Assume completion unless a state returns that isn't complete
        state["session_active"] = task.status.state not in [
            TaskState.COMPLETED,
            TaskState.CANCELED,
            TaskState.FAILED,
            TaskState.UNKNOWN,
        ]
        if task.status.state == TaskState.INPUT_REQUIRED:
            # Force user input back
            tool_context.actions.skip_summarization = True
            tool_context.actions.escalate = True
        elif task.status.state == TaskState.CANCELED:
            # Open question, should we return some info for cancellation instead
            raise ValueError(f"Agent {agent_name} task {task.id} is cancelled")
        elif task.status.state == TaskState.FAILED:
            # Raise error for failure
            raise ValueError(f"Agent {agent_name} task {task.id} failed")
        response = []
        if task.status.message:
            # Assume the information is in the task message.
            response.extend(convert_parts(task.status.message.parts, tool_context))
        if task.artifacts:
            for artifact in task.artifacts:
                response.extend(convert_parts(artifact.parts, tool_context))
        return response


def convert_parts(parts: list[Part], tool_context: ToolContext):
    rval = []
    for p in parts:
        rval.append(convert_part(p, tool_context))
    return rval


def convert_part(part: Part, tool_context: ToolContext):
    if part.type == "text":
        return part.text
    elif part.type == "data":
        return part.data
    elif part.type == "file":
        # Repackage A2A FilePart to google.genai Blob
        # Currently not considering plain text as files
        file_id = part.file.name
        file_bytes = base64.b64decode(part.file.bytes)
        file_part = types.Part(
            inline_data=types.Blob(mime_type=part.file.mimeType, data=file_bytes)
        )
        tool_context.save_artifact(file_id, file_part)
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        return DataPart(data={"artifact-file-id": file_id})
    return f"Unknown type: {p.type}"
