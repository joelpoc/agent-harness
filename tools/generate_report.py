"""generate_report — formats query results into a markdown report."""

from __future__ import annotations

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry


class GenerateReportInput(ToolInput):
    title: str = Field(description="Report title")
    content: str = Field(description="Report body in markdown")
    format: str = Field(default="markdown", description="Output format: markdown | text")


class GenerateReportOutput(ToolOutput):
    report: str = ""


async def _report_handler(
    title: str, content: str, format: str = "markdown"
) -> GenerateReportOutput:
    report = f"# {title}\n\n{content}"
    return GenerateReportOutput(success=True, report=report)


registry.register(
    ToolDefinition(
        name="generate_report",
        description="Format data and analysis into a structured markdown report.",
        input_schema=GenerateReportInput,
        output_schema=GenerateReportOutput,
        handler=_report_handler,  # type: ignore[arg-type]
        tags=["output"],
    )
)
