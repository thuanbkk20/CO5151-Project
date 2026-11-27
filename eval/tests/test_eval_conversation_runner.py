"""The conversation runner with a fake agent: history per conversation, prefill, new conversation, summaries."""

from co5151_eval.agent import AgentResponse
from co5151_eval.conversation_runner import conversation_passed, run_conversations, summarize_conversations
from co5151_eval.conversations import load_conversations
from co5151_eval.tasks import Outcome


class Recorder:
    """Answers every turn with its expected outcome (turns come in the order of the set) and remembers the history."""

    name = "recorder"

    def __init__(self, expected):
        self.expected = expected  # an iterator shared by the agents of one run
        self.calls = []

    def answer(self, question, *, session_token, history):
        self.calls.append((question, list(history), session_token))
        outcome = next(self.expected)
        text = "Hội thoại này đã đủ 10 câu hỏi." if outcome is Outcome.LIMIT else "ok"
        return AgentResponse(text=text, outcome=outcome)


def test_all_twenty_conversations_run_with_their_history():
    conversations = load_conversations()
    expected = iter([t.expected for c in conversations for t in c.turns] * 2)
    agents = []

    def factory(seed):
        agents.append(Recorder(expected))
        return agents[-1]

    records = run_conversations(factory, conversations, seeds=[0, 1])
    assert len(records) == 124 and len(agents) == 40 and all(r.error is None for r in records)
    h01 = agents[0].calls
    assert [len(h) for _, h, _ in h01] == [0, 2, 4] and h01[1][1][0]["content"] == conversations[0].turns[0].question
    h18 = next(a for a in agents[:20] if a.calls[0][0].startswith("Em còn bao nhiêu"))
    assert [len(h) for _, h, _ in h18.calls] == [20, 0]  # ten prefilled pairs, then a new conversation
    assert all(token for a in agents for _, _, token in a.calls)  # every conversation is signed in


def test_summary_by_turn_conversation_and_use_case():
    conversations = load_conversations()
    expected = iter([t.expected for c in conversations for t in c.turns])
    records = run_conversations(lambda seed: Recorder(expected), conversations)
    summary = summarize_conversations(records)
    assert summary["turns"]["turns"] == 62 and summary["turns"]["outcome_accuracy"] == 1.0
    assert summary["turns"]["limit_ok"] == 1.0 and summary["turns"]["false_refusal_rate"] == 0.0
    assert set(summary["by_use_case"]) == {f"UC{i}" for i in range(1, 10)}
    assert summary["by_use_case"]["UC9"]["conversations"] == 1 and len(summary["by_conversation"]) == 20
    # "ok" mentions no fact: turns with facts fail, so does their conversation
    assert summary["by_conversation"]["H05"] == [False] and summary["by_conversation"]["H14"] == [True]


def test_conversation_verdict():
    class R:
        def __init__(self, passed):
            self.passed = passed

    assert conversation_passed([R(True), R(True)]) is True
    assert conversation_passed([R(True), R(None)]) is None
    assert conversation_passed([R(None), R(False)]) is False
