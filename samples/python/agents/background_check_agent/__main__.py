import logging

import click
from common.server import A2AServer
from common.types import AgentCapabilities, AgentCard, AgentSkill
from common.utils.push_notification_auth import PushNotificationSenderAuth
from dotenv import load_dotenv

from agents.background_check_agent.task_manager import TaskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10019)
def main(host, port):
    """Starts the Background Check Agent server using A2A."""
    # Build the agent card
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    skill_background_check = AgentSkill(
        id="background_check_agent",
        name="Background Verification Agent",
        description=(
            "Verify candidate credentials including universities, companies, and projects. "
            "Provides comprehensive background check reports for hiring decisions."
        ),
        tags=["background-check", "verification", "credentials"],
        examples=[
            "Verify this candidate: John Smith, graduated from MIT, worked at Google, claims AI project experience.",
            "Check background: Jane Doe, Stanford PhD, Tesla engineer, published 10 papers on machine learning.",
        ],
    )

    agent_card = AgentCard(
        name="Background Check Agent",
        description=(
            "Comprehensive background verification agent for candidate screening. "
            "Verifies universities, companies, and project claims using specialized tools."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=capabilities,
        skills=[skill_background_check],
    )

    # Prepare push notification system
    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    # Create the server
    task_manager = TaskManager(notification_sender_auth=notification_sender_auth)
    server = A2AServer(
        agent_card=agent_card, task_manager=task_manager, host=host, port=port
    )
    server.app.add_route(
        "/.well-known/jwks.json",
        notification_sender_auth.handle_jwks_endpoint,
        methods=["GET"],
    )

    logger.info(f"Starting the Background Check agent server on {host}:{port}")
    server.start()


if __name__ == "__main__":
    main()
