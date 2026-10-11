"""Small RFC-style robots matcher with wildcard and longest-rule support."""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass
class Group:
    """Rules belonging to one sequence of user-agent directives."""

    agents: list[str] = field(default_factory=list)
    rules: list[tuple[str, bool]] = field(default_factory=list)
    delay: float = 0.0
    has_directives: bool = False


class RobotsPolicy:
    """Combine equally specific agent groups; Allow wins equal-length ties."""

    def __init__(self, text: str, agent: str = "idlink") -> None:
        groups: list[Group] = []
        group = Group()
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if group.has_directives:
                    groups.append(group)
                    group = Group()
                group.agents.append(value.lower())
            elif group.agents:
                group.has_directives = True
                if key in {"allow", "disallow"} and value:
                    group.rules.append((value, key == "allow"))
                elif key == "crawl-delay":
                    try:
                        delay = float(value)
                        if 0 <= delay <= 3600:
                            group.delay = max(group.delay, delay)
                        else:
                            raise ValueError("invalid crawl delay")
                    except ValueError as exc:
                        raise ValueError("unusable robots crawl-delay") from exc
                elif key == "request-rate":
                    requests, _, seconds = value.partition("/")
                    if requests.isdigit() and seconds.isdigit() and int(requests) > 0:
                        group.delay = max(group.delay, int(seconds) / int(requests))
        if group.agents:
            groups.append(group)

        def specificity(g: Group) -> int:
            return max(
                (0 if a == "*" else len(a) for a in g.agents if a == "*" or a in agent.lower()),
                default=-1,
            )

        highest = max((specificity(g) for g in groups), default=-1)
        selected = [g for g in groups if specificity(g) == highest]
        self.rules = [rule for g in selected for rule in g.rules]
        self.delay = max((g.delay for g in selected), default=0.0)

    def can_fetch(self, url: str) -> bool:
        """Apply path/query wildcard rules and optional terminal dollar anchors."""
        parsed = urlsplit(url)
        target = unquote(parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        matches: list[tuple[int, bool]] = []
        for pattern, allow in self.rules:
            anchored = pattern.endswith("$")
            pattern = unquote(pattern[:-1] if anchored else pattern)
            expression = "^" + ".*".join(re.escape(part) for part in pattern.split("*"))
            if anchored:
                expression += "$"
            if re.search(expression, target):
                matches.append((len(pattern.replace("*", "")), allow))
        return max(matches, default=(0, True))[1]
