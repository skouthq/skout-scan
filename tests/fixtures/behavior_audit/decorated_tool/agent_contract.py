class AgentContract:
    def __init__(self, functions):
        self.capabilities = {function.__name__: function for function in functions}

    def invoke(self, capability, *args, **kwargs):
        return self.capabilities[capability](*args, **kwargs)


def create_agent(*, tools):
    return AgentContract(tools)
