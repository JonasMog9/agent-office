"""A scripted stand-in for ``anthropic.Anthropic``: no network, no cost, repeatable.

Each model gets a queue of replies. A reply is a list of blocks: ``("text", "...")`` or
``("tool", name, {input})``; a reply with any tool block stops with ``tool_use``. Every
request is recorded so tests can check what was sent (models, tools, tool results).
"""

from collections import defaultdict
from types import SimpleNamespace


def reply(*blocks, stop_reason: str | None = None) -> SimpleNamespace:
    content = []
    for i, b in enumerate(blocks):
        if b[0] == "text":
            content.append(SimpleNamespace(type="text", text=b[1]))
        else:
            content.append(
                SimpleNamespace(type="tool_use", id=f"tu_{b[1]}_{i}", name=b[1], input=b[2])
            )
    has_tool = any(b[0] == "tool" for b in blocks)
    return SimpleNamespace(
        content=content, stop_reason=stop_reason or ("tool_use" if has_tool else "end_turn")
    )


class _Messages:
    def __init__(self, owner: "FakeClaude", beta: bool) -> None:
        self.owner, self.beta = owner, beta

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        # Copy the message list: the loop keeps appending to the same list object.
        self.owner.requests.append(
            kwargs | {"messages": list(kwargs["messages"]), "beta": self.beta}
        )
        queue = self.owner.script[kwargs["model"]]
        if not queue:
            raise AssertionError(f"no scripted reply left for {kwargs['model']}")
        return queue.pop(0)


class FakeClaude:
    def __init__(self, script: dict[str, list]) -> None:
        self.script = defaultdict(list, {k: list(v) for k, v in script.items()})
        self.requests: list[dict] = []
        self.messages = _Messages(self, beta=False)
        self.beta = SimpleNamespace(messages=_Messages(self, beta=True))

    def tool_results(self, model: str) -> list[dict]:
        """Every tool_result block sent to ``model``."""
        out = []
        for r in self.requests:
            if r["model"] != model:
                continue
            last = r["messages"][-1]
            if isinstance(last["content"], list):
                out += [b for b in last["content"] if b.get("type") == "tool_result"]
        return out
