from langchain_core.tools import tool


class First:
    def execute(self, value):
        return value


class Second:
    def execute(self, value):
        return value


adapter = First()
adapter = Second()


@tool
def run(value):
    return adapter.execute(value)
