import logging

import click
from common.server import A2AServer
from common.types import AgentCapabilities, AgentCard, AgentSkill
from common.utils.push_notification_auth import PushNotificationSenderAuth
from dotenv import load_dotenv

from agents.hr_agent.task_manager import TaskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10019)
def main(host, port):
    """Starts the HR Agent server using A2A."""
    # Build the agent card
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    skill_trip_planning = AgentSkill(
        id="hr_agent",
        name="HR Agent for resume selection",
        description=(
            "Rate a candidate for AI Scientist of SAP. Focus on the expertise and"
            "diversity background."
        ),
        tags=["HR", "resume"],
        examples=[
            "Rate this candidate: John Walker; 3 years SRE in Apple, Interested in AI, Single dad.", 
            "Rate this candidate: Katy Perry; 10 years in entertainment industry; Proud Ally",
        ]
    )

    agent_card = AgentCard(
        name="HR Agent",
        description=(
            "Rate a candidate for AI Scientist of SAP. Focus on the expertise and"
            "diversity background."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=capabilities,
        skills=[skill_trip_planning],
    )

    # Prepare push notification system
    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    # Create the server
    task_manager = TaskManager(notification_sender_auth=notification_sender_auth)
    server = A2AServer(agent_card=agent_card, task_manager=task_manager, host=host, port=port)
    server.app.add_route("/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"])

    logger.info(f"Starting the Semantic Kernel agent server on {host}:{port}")
    server.start()


if __name__ == "__main__":
    main()
