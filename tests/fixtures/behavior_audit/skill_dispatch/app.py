from agent_contract import create_agent
from langchain_core.tools import tool


def summarize(text: str) -> str:
    return text[:80]


def translate(text: str) -> str:
    return text.upper()


CAPABILITIES = {"summarize": summarize, "translate": translate}


@tool
def dispatch_skill(name: str, text: str) -> str:
    return CAPABILITIES[name](text)


agent = create_agent(tools=[dispatch_skill])
