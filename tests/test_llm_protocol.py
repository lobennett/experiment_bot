from experiment_bot.llm.protocol import LLMClient, LLMResponse


def test_llm_client_is_a_protocol():
    assert hasattr(LLMClient, "complete")


def test_llm_response_is_a_dataclass():
    r = LLMResponse(text="hi", stop_reason="end_turn")
    assert r.text == "hi"
    assert r.stop_reason == "end_turn"


def test_llm_response_default_stop_reason():
    r = LLMResponse(text="x")
    assert r.stop_reason == "end_turn"
