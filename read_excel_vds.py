import openpyxl
import sys
import os

base = "C:/workspace/Artifact Virtual/01_Valkyrie Data Systems"

files = [
    f"{base}/CAPEX/CAPEX_Model.xlsx",
    f"{base}/OPEX/OPEX_Model.xlsx",
    f"{base}/Audit/Investor_Financial_Model_and_Audit.xlsx"
]

for filepath in files:
    print(f"\n{'='*70}")
    print(f"FILE: {os.path.basename(filepath)}")
    print('='*70)
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        for ws in wb.worksheets:
            print(f"\n--- Sheet: {ws.title} ---")
            row_count = 0
            for row in ws.iter_rows(max_row=100, max_col=20):
                row_data = []
                has_data = False
                for cell in row:
                    val = cell.value
                    if val is not None:
                        has_data = True
                    row_data.append(str(val) if val is not None else "")
                if has_data:
                    print(" | ".join(row_data))
                    row_count += 1
                if row_count > 80:
                    print("... [truncated]")
                    break
    except Exception as e:
        print(f"Error: {e}")
