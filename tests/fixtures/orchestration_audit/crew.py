import crewai as crew
from crewai import Agent as Worker
from crewai import Task as Assignment

first = Worker(role="reader")
second = crew.Agent(role="writer")
read = Assignment(description="read", agent=first)
inspect = crew.Task(description="inspect", agent=first, context=[read])
write = Assignment(description="write", agent=second, context=[inspect])
context_only = Assignment(description="context", context=[write])
