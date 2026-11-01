from pydantic_ai import Agent


class First:
    def read(self, value):
        return value


class Second:
    def read(self, value):
        return value


first = First()
second = Second()
alpha = Agent("test", tools=[first.read])
beta = Agent("test", tools=[second.read])
