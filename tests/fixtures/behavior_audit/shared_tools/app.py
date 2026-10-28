from agent_contract import create_agent


def read_record(key: str) -> str:
    return key


first_agent = create_agent(tools=[read_record])
second_agent = create_agent(tools=[read_record])
