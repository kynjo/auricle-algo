from pathlib import Path

from help_content import ALGORITHMS, PROCESSES, help_html


def test_help_is_external_module_and_bilingual():
    html_en = help_html("en")
    html_ru = help_html("ru")
    assert "Quick start" in html_en
    assert "Быстрый старт" in html_ru
    assert "Relations" in html_en
    assert "Perform" in html_en
    assert "Process Layers" in html_en
    assert "Relations" in html_ru
    assert len(html_en) > 9000
    assert len(html_ru) > 9000


def test_all_generator_and_process_catalog_entries_are_documented():
    assert len(ALGORITHMS) == 19
    assert len(PROCESSES) == 9
    for name, (en, ru) in ALGORITHMS.items():
        assert name in help_html("en")
        assert en and ru
    for name, (en, ru) in PROCESSES.items():
        assert name in help_html("en")
        assert en and ru


def test_gui_uses_external_help_module_and_language_selector():
    source = Path(__file__).parents[1].joinpath("auricle_gui.py").read_text(encoding="utf-8")
    assert "from help_content import help_html" in source
    assert 'self.help_language.addItem("English", "en")' in source
    assert 'self.help_language.addItem("Русский", "ru")' in source
    assert 'self.help_view.setHtml(help_html(language or "en"))' in source
    # Documentation must not be embedded as the old large HTML block.
    assert "<h3>Relations</h3>" not in source
