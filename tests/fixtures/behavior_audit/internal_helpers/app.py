def format_message(value: str) -> str:
    return f"Record: {value}"


def transform_record(value: str) -> str:
    if value:
        return value.strip()
    return "empty"


def log_record(value: str) -> None:
    print(value)
