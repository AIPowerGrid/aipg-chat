"""Tests for ``ImageGenerationTool._resolve_reference_image_file_ids``.

The resolver turns the LLM's ``reference_image_file_ids`` argument into a
cleaned list of file IDs to hand to ``_load_reference_images``. It trusts
the LLM's picks — the LLM can only see file IDs that actually appear in
the conversation (via ``[attached image — file_id: <id>]`` tags on user
messages and the JSON returned by prior generate_image calls), so we
don't re-validate against an allow-list in the tool itself.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from onyx.tools.models import ToolCallException
from onyx.tools.models import ToolExecutionException
from onyx.tools.tool_implementations.images.image_generation_tool import (
    ImageGenerationTool,
)
from onyx.tools.tool_implementations.images.image_generation_tool import (
    REFERENCE_IMAGE_FILE_IDS_FIELD,
)
from onyx.tools.tool_implementations.images.models import ImageShape


def _make_tool(
    supports_reference_images: bool = True,
    max_reference_images: int = 16,
) -> ImageGenerationTool:
    """Construct a tool with a mock provider so no credentials/network are needed."""
    with patch(
        "onyx.tools.tool_implementations.images.image_generation_tool.get_image_generation_provider"
    ) as mock_get_provider:
        mock_provider = MagicMock()
        mock_provider.supports_reference_images = supports_reference_images
        mock_provider.max_reference_images = max_reference_images
        mock_get_provider.return_value = mock_provider

        return ImageGenerationTool(
            image_generation_credentials=MagicMock(),
            tool_id=1,
            emitter=MagicMock(),
            model="gpt-image-1",
            provider="openai",
        )


class TestResolveReferenceImageFileIds:
    def test_unset_returns_empty_plain_generation(self) -> None:
        tool = _make_tool()
        assert tool._resolve_reference_image_file_ids(llm_kwargs={}) == []

    def test_empty_list_is_treated_like_unset(self) -> None:
        tool = _make_tool()
        result = tool._resolve_reference_image_file_ids(
            llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: []},
        )
        assert result == []

    def test_passes_llm_supplied_ids_through(self) -> None:
        tool = _make_tool()
        result = tool._resolve_reference_image_file_ids(
            llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["upload-1", "gen-1"]},
        )
        # Order preserved — first entry is the primary edit source.
        assert result == ["upload-1", "gen-1"]

    def test_invalid_shape_raises(self) -> None:
        tool = _make_tool()
        with pytest.raises(ToolCallException):
            tool._resolve_reference_image_file_ids(
                llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: "not-a-list"},
            )

    def test_non_string_element_raises(self) -> None:
        tool = _make_tool()
        with pytest.raises(ToolCallException):
            tool._resolve_reference_image_file_ids(
                llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["ok", 123]},
            )

    def test_deduplicates_preserving_first_occurrence(self) -> None:
        tool = _make_tool()
        result = tool._resolve_reference_image_file_ids(
            llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["gen-1", "gen-2", "gen-1"]},
        )
        assert result == ["gen-1", "gen-2"]

    def test_strips_whitespace_and_skips_empty_strings(self) -> None:
        tool = _make_tool()
        result = tool._resolve_reference_image_file_ids(
            llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["  gen-1  ", "", "   "]},
        )
        assert result == ["gen-1"]

    def test_provider_without_reference_support_raises(self) -> None:
        tool = _make_tool(supports_reference_images=False)
        with pytest.raises(ToolCallException):
            tool._resolve_reference_image_file_ids(
                llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["gen-1"]},
            )

    def test_truncates_to_provider_max_preserving_head(self) -> None:
        """When the LLM lists more images than the provider allows, keep the
        HEAD of the list (the primary edit source + earliest extras) rather
        than the tail, since the LLM put the most important one first."""
        tool = _make_tool(max_reference_images=2)
        result = tool._resolve_reference_image_file_ids(
            llm_kwargs={REFERENCE_IMAGE_FILE_IDS_FIELD: ["a", "b", "c", "d"]},
        )
        assert result == ["a", "b"]


def test_image_requests_refresh_and_forward_delegated_headers() -> None:
    tool = _make_tool()
    factory = MagicMock(
        side_effect=[
            {"X-Grid-User-Token": "gridu_first"},
            {"X-Grid-User-Token": "gridu_refreshed"},
        ]
    )
    tool._extra_headers_factory = factory
    image = MagicMock()
    image.model_dump.return_value = {"b64_json": "dGVzdA=="}
    generate_image = tool.img_provider.generate_image
    assert isinstance(generate_image, MagicMock)
    generate_image.return_value = MagicMock(data=[image])
    tool._generate_image("first", ImageShape.SQUARE)
    tool._generate_image("second", ImageShape.SQUARE)
    assert factory.call_count == 2
    assert [call.kwargs["extra_headers"] for call in generate_image.call_args_list] == [
        {"X-Grid-User-Token": "gridu_first"},
        {"X-Grid-User-Token": "gridu_refreshed"},
    ]


def test_image_identity_exchange_failure_never_calls_provider() -> None:
    tool = _make_tool()
    tool._extra_headers_factory = MagicMock(
        side_effect=RuntimeError("exchange unavailable")
    )
    with pytest.raises(ToolExecutionException):
        tool._generate_image("test", ImageShape.SQUARE)
    generate_image = tool.img_provider.generate_image
    assert isinstance(generate_image, MagicMock)
    generate_image.assert_not_called()
