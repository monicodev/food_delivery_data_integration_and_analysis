import pandas as pd
import os

excel_path = os.path.join(os.getcwd(), "source", "food_categories.xlsx")
if os.path.exists(excel_path):
    df = pd.read_excel(excel_path)
    print("Columns in Excel:", df.columns.tolist())
else:
    print("File not found.")
