#Test script to get balance sheet raw data from yahoo finance through yfinance package and 10-k report from SEC through sec-api package
import os
from dotenv import load_dotenv
from typing import Annotated
from pandas import DataFrame
from textwrap import dedent
from get_10k_base import SecReportFetcher
from sec_api import ExtractorApi
import yfinance as yf

# Load environment variables from .env file
load_dotenv()

#Define the API key of SEC
sec_api_key = os.environ.get("SEC_API_KEY")
if not sec_api_key:
    raise ValueError("SEC_API_KEY is not set in the environment variables")

#Define the returned class of ExtractorApi
extractor_api = ExtractorApi(sec_api_key)

#Define the cache path
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

#Define custom annotated types
SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

#Define the function to combine the instruction, resource, and table
def combine_prompt(instruction, resource, table_str=None):
    if table_str:
        prompt = f"{table_str}\n\nResource: {resource}\n\nInstruction: {instruction}"
    else:
        prompt = f"Resource: {resource}\n\nInstruction: {instruction}"
    return prompt


def save_to_file(data: str, file_path: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write(data)

#This to get the balance sheet from yahoo finance, not from SEC 10-k report
def get_balance_sheet(symbol: Annotated[str, "ticker symbol"]) -> DataFrame:
    """Fetches and returns the latest balance sheet of the company as a DataFrame."""
    ticker = yf.Ticker(symbol) # Create a Ticker object instead of using the string directly
    balance_sheet = ticker.balance_sheet
    return balance_sheet

def get_10k_section(
        ticker_symbol: Annotated[str, "ticker symbol"],
        fyear: Annotated[str, "fiscal year of the 10-K report"],
        section: Annotated[str | int, 
                           "Section of the 10-K report to extract, should be in [1, 1A, 1B, 2, 3, 4, 5, 6, 7, 7A, 8, 9, 9A, 9B, 10, 11, 12, 13, 14, 15]"
        ],
        report_address: Annotated[
            str,
            "URL of the 10-K report, if not specified, will get report url from fmp api"
        ] = None,
        save_path: SavePathType = None, # In this context, save_path=None is a valid default value, indicating that the file will not be saved by default unless a specific path is provided.

) -> str:
    """
    Get a specific section of a 10-K report from the SEC API.
    """
    if isinstance(section, int):
        section = str(section)
    if section not in [
            "1A",
            "1B",
            "7A",
            "9A",
            "9B",        
    ] + [str(i) for i in range(1, 16)]:
        raise ValueError(
            "Section must be in [1, 1A, 1B, 2, 3, 4, 5, 6, 7, 7A, 8, 9, 9A, 9B, 10, 11, 12, 13, 14, 15]"
        )
    
    if report_address is None:
        report_address = SecReportFetcher().get_sec_report(ticker_symbol, fyear)
        if report_address.startswith("Link: "):
            report_address = report_address.lstrip("Link: ").split()[0]
        else:
            return report_address  # debug info

    cache_path = os.path.join(
        CACHE_PATH, f"sec_utils/{ticker_symbol}_{fyear}_{section}.txt"
    )

    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            section_text = f.read()
    else:
        section_text = extractor_api.get_section(report_address, section, "text")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(section_text)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w") as f:
            f.write(section_text)

    return section_text


def analyze_balance_sheet(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the 10-K report"],
    save_path: Annotated[str, "txt file path, to which the returned instruction & resources are written."]
) -> tuple[str, str]:
    """
    Retrieve the balance sheet for the given ticker symbol with the related section of its 10-K report.
    Then return with an instruction on how to analyze the balance sheet.
    Returns:
        tuple: (prompt, save_status)
    """
    # Get balance sheet data
    print("Fetching balance sheet data...")
    balance_sheet = get_balance_sheet(ticker_symbol)
    df_string = "Balance sheet:\n" + balance_sheet.to_string().strip()

    # Get instruction
    instruction = dedent(
        """
        Analyze the following balance sheet data and 10-K report section:
        1. Evaluate the company's financial stability by analyzing assets, liabilities, and equity structure
        2. Assess liquidity through current assets vs. current liabilities
        3. Examine solvency via long-term debt ratios
        4. Compare with previous years to identify trends
        5. Provide a strategic assessment of financial leverage and capital structure
        
        Provide a comprehensive analysis in a well-structured response.
        """
    )

    # Retrieve the related section from the 10-K report
    print("Fetching 10-K report section...")
    section_text = get_10k_section(ticker_symbol, fyear, 7, save_path=None)  # Don't save section separately

    # Combine all components into the prompt, the prompt has balance sheet data(df_string), 10-K report section(section_text), and LLM instruction(instruction)
    prompt = combine_prompt(instruction, section_text, df_string) #根据生成的balance_sheet_analysis.txt显示，最左边的参数结果显示在最下面，最右边的参数结果显示在最上面。代表显示顺序是从右到左。

    # Save the complete prompt text to a file as the raw balance sheet info file
    save_to_file(prompt, save_path)
    
    return prompt, f"Data and instructions saved to {save_path}" #This is to generate the output file 

if __name__ == "__main__":
    # Get user input with guidance
    ticker = input("Enter company ticker symbol (e.g., AAPL, TSLA): ").strip().upper()
    fyear = input("Enter fiscal year for 10-K report (e.g., 2023): ").strip()
    #set the default path to have ticker symbol and fyear
    default_path = f"{ticker}_{fyear}_balance_sheet_analysis.txt"
    save_path = input(f"Enter save path [default: {default_path}]: ").strip() or default_path

    # Execute analysis with user parameters
    result = analyze_balance_sheet(ticker, fyear, save_path)
    print(f"\nAnalysis completed: {result[1]}")