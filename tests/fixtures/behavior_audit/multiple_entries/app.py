from pydantic_ai import Agent


class RecordsAdapter:
    def read(self, key: str) -> str:
        return key


class AuditAdapter:
    def append(self, event: str) -> str:
        return event


records = RecordsAdapter()
audit = AuditAdapter()
reader = Agent("test", tools=[records.read])
writer = Agent("test", tools=[audit.append])
