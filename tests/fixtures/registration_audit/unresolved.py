from external_plugin import Client, create_agent, load_plugins
from pydantic_ai import Agent


def read(key: str) -> str:
    return key


class Records:
    def read(self, key: str) -> str:
        return key


records = Records()
records = Records()
client = Client()
ambiguous = Agent("test", tools=[records.read])
external = Agent("test", tools=[client.read])
dynamic = Agent("test", tools=load_plugins())
custom = create_agent(tools=[read])
