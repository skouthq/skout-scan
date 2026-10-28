"""Curated source, inspected statically. No framework installation is required."""

from langchain_core.tools import tool


def search(query):
    return query


def retrieve(query):
    return query


HANDLERS = {"search": search, "retrieve": retrieve, "lookup": search}


@tool
def dispatch_skill(key, query):
    return HANDLERS[key](query)


def unregistered(key, query):
    return HANDLERS[key](query)
