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


def test_llm_client_protocol_accepts_images_parameter():
    """Concrete clients must accept an optional images=list[bytes] parameter.
    The Protocol uses default None so existing callers stay compatible."""
    import inspect
    from experiment_bot.llm.protocol import LLMClient

    sig = inspect.signature(LLMClient.complete)
    assert "images" in sig.parameters
    assert sig.parameters["images"].default is None
