"""Spec §5. The fixed block must stay fixed."""

from zeroos.agent import prompt
from zeroos.platform import settings


def test_sir_variant_is_still_the_default_system_prompt():
    assert prompt.SYSTEM_PROMPT == prompt.PROMPTS["sir"]


def test_there_is_one_prompt_per_form_of_address():
    assert set(prompt.PROMPTS) == set(settings.ADDRESSES)


def test_the_variants_differ_only_in_the_address_line():
    sir = prompt.PROMPTS["sir"].splitlines()
    maam = prompt.PROMPTS["maam"].splitlines()
    differing = [i for i, (a, b) in enumerate(zip(sir, maam)) if a != b]
    assert len(differing) == 1
    assert len(sir) == len(maam)


def test_sir_variant_says_sir_and_the_others_do_not():
    assert "Sir" in prompt.PROMPTS["sir"]
    assert "Sir" not in prompt.PROMPTS["maam"]
    assert "Sir" not in prompt.PROMPTS["none"]
    assert "Ma'am" in prompt.PROMPTS["maam"]


def test_prompts_are_built_once_not_per_call():
    assert prompt.PROMPTS["sir"] is prompt.PROMPTS["sir"]


def test_no_prompt_contains_a_format_placeholder():
    for text in prompt.PROMPTS.values():
        assert "{" not in text


def test_the_memory_preface_says_memories_are_not_instructions():
    assert "not instructions" in prompt.MEMORY_PREFACE
