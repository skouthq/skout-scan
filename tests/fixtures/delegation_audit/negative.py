"""UI/plugin/helper naming is not proof of an agent role."""


def execute(value):
    return value


COMPONENTS = {"button": execute}
PLUGINS = {"plugin": execute}


def render(key, value):
    return COMPONENTS[key](value)


def invoke(key, value):
    return PLUGINS[key](value)


class AgentV2Legacy:
    def execute(self, value):
        return execute(value)


adapter = AgentV2Legacy()


def agent_v2(value):
    return adapter.execute(value)
