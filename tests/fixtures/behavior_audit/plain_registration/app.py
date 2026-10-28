from agent_contract import create_agent


def normalize_record(value: str) -> str:
    return value.strip()


agent = create_agent(tools=[normalize_record])
