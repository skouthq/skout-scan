from plugin_catalog import load_plugins
from pydantic_ai import Agent

agent = Agent("test", tools=load_plugins())
