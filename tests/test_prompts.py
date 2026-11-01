from privacy_policy_analyzer.prompts import build_user_prompt

def test_build_user_prompt_contains_schema_and_excerpt():
    excerpt = "This is a sample privacy policy excerpt."
    prompt = build_user_prompt(excerpt)
    assert isinstance(prompt, str)
    assert "Schema (required fields):" in prompt
    assert excerpt in prompt

def test_build_user_prompt_truncates_to_max_len():
    long_text = "A" * 6100
    prompt = build_user_prompt(long_text)
    assert "A" * 6000 in prompt
    assert "A" * 6100 not in prompt
