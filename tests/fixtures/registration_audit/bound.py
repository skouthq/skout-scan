from pydantic_ai import Agent


class Records:
    def read(self, key: str) -> str:
        return key


class Archive:
    async def read(self, key: str) -> str:
        return key


records = Records()
archive = Archive()
reader = Agent("test", tools=[records.read])
archivist = Agent("test", tools=[archive.read])
