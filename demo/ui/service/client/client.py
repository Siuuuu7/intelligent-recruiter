import httpx
from typing import Any
import json
import os
from service.types import (
    CreateConversationRequest,
    CreateConversationResponse,
    ListConversationRequest,
    ListConversationResponse,
    SendMessageRequest,
    SendMessageResponse,
    ListMessageRequest,
    ListMessageResponse,
    GetEventRequest,
    GetEventResponse,
    PendingMessageRequest,
    PendingMessageResponse,
    ListTaskRequest,
    ListTaskResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    AgentClientHTTPError,
    ListAgentRequest,
    ListAgentResponse,
    AgentClientJSONError,
    JSONRPCRequest,
    SendMessageWithFileRequest,
    SendMessageWithFileResponse,
)
import json


class ConversationClient:

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    async def send_message(self, payload: SendMessageRequest) -> SendMessageResponse:
        return SendMessageResponse(**await self._send_request(payload))

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url + "/" + request.method, json=request.model_dump()
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise AgentClientHTTPError(e.response.status_code, str(e)) from e
            except json.JSONDecodeError as e:
                raise AgentClientJSONError(str(e)) from e

    async def send_message_with_file(
        self, payload: SendMessageWithFileRequest, file_path: str = None
    ) -> SendMessageWithFileResponse:
        print(
            f"[DEBUG] Client: send_message_with_file called with file_path: {file_path}"
        )
        print(f"[DEBUG] Client: payload.params.metadata: {payload.params.metadata}")

        if (
            file_path
            and payload.params.metadata
            and "file_path" in payload.params.metadata
        ):
            print(f"[DEBUG] Client: Using multipart form data for file upload")
            # Handle actual file upload with multipart form data
            async with httpx.AsyncClient() as client:
                try:
                    files = {}
                    data = {"message": payload.model_dump_json()}
                    print(f"[DEBUG] Client: message JSON being sent: {data['message']}")

                    # Add file if file_path exists and file exists
                    actual_file_path = payload.params.metadata.get(
                        "file_path", file_path
                    )
                    if actual_file_path and os.path.exists(actual_file_path):
                        with open(actual_file_path, "rb") as f:
                            files["file"] = (
                                os.path.basename(actual_file_path),
                                f.read(),
                            )
                        print(
                            f"[DEBUG] Client: Added file to multipart: {os.path.basename(actual_file_path)}"
                        )

                    response = await client.post(
                        self.base_url + "/" + payload.method,
                        data=data,
                        files=files if files else None,
                    )
                    response.raise_for_status()
                    return SendMessageWithFileResponse(**response.json())
                except httpx.HTTPStatusError as e:
                    raise AgentClientHTTPError(e.response.status_code, str(e)) from e
                except json.JSONDecodeError as e:
                    raise AgentClientJSONError(str(e)) from e
        else:
            print(
                f"[DEBUG] Client: Using regular JSON request (no file or no file_path in metadata)"
            )
            # Fallback to regular JSON request
            return SendMessageWithFileResponse(**await self._send_request(payload))

    async def create_conversation(
        self, payload: CreateConversationRequest
    ) -> CreateConversationResponse:
        return CreateConversationResponse(**await self._send_request(payload))

    async def list_conversation(
        self, payload: ListConversationRequest
    ) -> ListConversationResponse:
        return ListConversationResponse(**await self._send_request(payload))

    async def get_events(self, payload: GetEventRequest) -> GetEventResponse:
        return GetEventResponse(**await self._send_request(payload))

    async def list_messages(self, payload: ListMessageRequest) -> ListMessageResponse:
        return ListMessageResponse(**await self._send_request(payload))

    async def get_pending_messages(
        self, payload: PendingMessageRequest
    ) -> PendingMessageResponse:
        return PendingMessageResponse(**await self._send_request(payload))

    async def list_tasks(self, payload: ListTaskRequest) -> ListTaskResponse:
        return ListTaskResponse(**await self._send_request(payload))

    async def register_agent(
        self, payload: RegisterAgentRequest
    ) -> RegisterAgentResponse:
        return RegisterAgentResponse(**await self._send_request(payload))

    async def list_agents(self, payload: ListAgentRequest) -> ListAgentResponse:
        return ListAgentResponse(**await self._send_request(payload))
