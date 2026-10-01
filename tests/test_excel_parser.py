import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl

from src.excel_parser import _extract_refs, parse_workbook


class ExtractRefsTests(unittest.TestCase):
    def test_expands_cross_sheet_range(self):
        self.assertEqual(
            _extract_refs("=SUM(Forecast!B2:B4)", "Summary"),
            ["Forecast!B2", "Forecast!B3", "Forecast!B4"],
        )

    def test_handles_absolute_and_quoted_sheet_reference(self):
        self.assertEqual(
            _extract_refs("='Sheet Name'!$A$1", "Summary"),
            ["Sheet Name!A1"],
        )

    def test_uses_current_sheet_for_local_range(self):
        self.assertEqual(
            _extract_refs("=AVERAGE(C2:C4)", "Forecast"),
            ["Forecast!C2", "Forecast!C3", "Forecast!C4"],
        )

    def test_large_range_only_includes_known_cells_inside_bounds(self):
        self.assertEqual(
            _extract_refs(
                "=SUM(A:A)",
                "Forecast",
                ["Forecast!A1", "Forecast!A20", "Forecast!B1", "Summary!A1"],
            ),
            ["Forecast!A1", "Forecast!A20"],
        )


class ParseWorkbookTests(unittest.TestCase):
    def test_sample_summary_dependencies_are_expanded_without_phantom_nodes(self):
        with TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "business_planning_sample.xlsx"
            workbook = openpyxl.Workbook()
            forecast = workbook.active
            forecast.title = "Forecast"
            for row in range(2, 5):
                forecast[f"B{row}"] = row
                forecast[f"C{row}"] = row / 10
            summary = workbook.create_sheet("Summary")
            summary["B1"] = "=SUM(Forecast!B2:B4)"
            summary["B2"] = "=AVERAGE(Forecast!C2:C4)"
            workbook.save(workbook_path)

            model = parse_workbook(str(workbook_path))

        self.assertEqual(
            set(model.graph.predecessors("Summary!B1")),
            {"Forecast!B2", "Forecast!B3", "Forecast!B4"},
        )
        self.assertEqual(
            set(model.graph.predecessors("Summary!B2")),
            {"Forecast!C2", "Forecast!C3", "Forecast!C4"},
        )
        self.assertEqual(len(model.graph), len(model.cells))


if __name__ == "__main__":
    unittest.main()