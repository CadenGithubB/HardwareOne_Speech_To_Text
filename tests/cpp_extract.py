"""Read production definitions for host harnesses; no policy copies."""
def extract_block(source: str, marker: str) -> str:
    """Extract an actual C++ definition, ignoring braces in comments/literals."""
    start = source.index(marker)
    opening = source.index("{", start + len(marker))
    pos, depth, state = opening, 0, "code"
    while pos < len(source):
        char = source[pos]
        following = source[pos + 1 : pos + 2]
        if state == "line":
            if char == "\n":
                state = "code"
        elif state == "comment":
            if char == "*" and following == "/":
                state = "code"
                pos += 1
        elif state in ("string", "character"):
            if char == "\\":
                pos += 1
            elif char == ('"' if state == "string" else "'"):
                state = "code"
        elif char == "/" and following == "/":
            state = "line"
            pos += 1
        elif char == "/" and following == "*":
            state = "comment"
            pos += 1
        elif char in ('"', "'"):
            state = "string" if char == '"' else "character"
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : pos + 1]
        pos += 1
    raise AssertionError(f"unterminated production definition: {marker}")
