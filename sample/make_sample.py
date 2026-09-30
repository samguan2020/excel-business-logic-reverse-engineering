"""
Generates a synthetic finance workbook for local smoke testing.
All values and metadata are fictional and contain no customer records.

Run: python sample/make_sample.py
"""
import openpyxl

wb = openpyxl.Workbook()
wb.properties.creator = "Finance Example"
wb.properties.lastModifiedBy = "Finance Example"
wb.properties.title = "Synthetic Finance Workbook"
wb.properties.description = "Fictional sample data for finance workbook reverse engineering."

inputs = wb.active
inputs.title = "Inputs"
inputs["A1"] = "Month"
inputs["B1"] = "Revenue"
inputs["C1"] = "COGS"
data = [
    ("Jan", 100000, 40000),
    ("Feb", 110000, 42000),
    ("Mar", 105000, 41000),
]
for i, (m, r, c) in enumerate(data, start=2):
    inputs[f"A{i}"] = m
    inputs[f"B{i}"] = r
    inputs[f"C{i}"] = c

forecast = wb.create_sheet("Forecast")
forecast["A1"] = "Month"
forecast["B1"] = "Gross Profit"
forecast["C1"] = "Margin %"
forecast["D1"] = "YoY Growth"
for i in range(2, 5):
    forecast[f"A{i}"] = f"=Inputs!A{i}"
    forecast[f"B{i}"] = f"=Inputs!B{i}-Inputs!C{i}"
    forecast[f"C{i}"] = f"=B{i}/Inputs!B{i}"
forecast["D3"] = "=(Inputs!B3-Inputs!B2)/Inputs!B2"
forecast["D4"] = "=(Inputs!B4-Inputs!B3)/Inputs!B3"

summary = wb.create_sheet("Summary")
summary["A1"] = "Total Gross Profit"
summary["B1"] = "=SUM(Forecast!B2:B4)"
summary["A2"] = "Avg Margin %"
summary["B2"] = "=AVERAGE(Forecast!C2:C4)"
summary["B2"].comment = openpyxl.comments.Comment(
    "Finance team uses this as the board-reported margin KPI.", "SME"
)

wb.save("sample/finance_sample.xlsx")
print("Wrote sample/finance_sample.xlsx")
