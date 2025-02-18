#Test script to get balance sheet raw data from yahoo finance through yfinance package and 10-k report from SEC through sec-api package
import os
from dotenv import load_dotenv
from typing import Annotated
from pandas import DataFrame
from textwrap import dedent
from get_10k_base import SecReportFetcher
from sec_api import ExtractorApi
import yfinance as yf
import asyncio
from autogen import ConversableAgent

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
    # Get directory path
    directory = os.path.dirname(file_path)
    
    # Create directory if it's not empty and doesn't exist
    if directory:  # This checks if directory is not an empty string
        os.makedirs(directory, exist_ok=True)
    
    # Write the file
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

# Add this new function for LLM analysis
async def analyze_with_llm(prompt: str, api_key: str) -> str:
    """
    Analyze the balance sheet data using LLM through AutoGen.
    """
    agent = ConversableAgent(
        name="BalanceSheetAnalyzer",
        system_message="""You are an expert financial analyst. Your task is to analyze the provided financial statements data and 10-K report information directly.
        DO NOT try to fetch new data or call any functions. Instead, analyze the data that is provided to you in the prompt.
        
        Provide a detailed analysis that includes:
        1. Financial Position Analysis
        2. Liquidity Assessment
        3. Solvency Analysis
        4. Year-over-Year Trends
        5. Strategic Insights
        
        Use specific numbers and ratios from the provided data in your analysis.""",
        human_input_mode="NEVER",
        llm_config={
            "config_list": [
                {
                    "model": "deepseek-chat",
                    "api_key": api_key,
                    "base_url": "https://api.deepseek.com/v1",
                }
            ],
            "temperature": 1.3,
            "timeout": 120,
        },
        function_map=None
    )

    try:
        response = await agent.a_generate_reply(
            messages=[{"role": "user", "content": prompt}],
            sender=agent
        )
        return response.get('content', str(response)) if isinstance(response, dict) else str(response)
    except Exception as e:
        return f"Error during analysis: {str(e)}"

# Modify analyze_balance_sheet to be async and include LLM analysis
async def analyze_balance_sheet(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the 10-K report"],
    save_path: Annotated[str, "txt file path, to which the returned instruction & resources are written."],
    llm_api_key: str = None
) -> tuple[str, str]:
    """
    Retrieve and analyze the balance sheet for the given ticker symbol.
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
    section_text = get_10k_section(ticker_symbol, fyear, 7, save_path=None)

    # Combine all components into the prompt
    prompt = combine_prompt(instruction, section_text, df_string)

    # Save the initial data and instructions
    save_to_file(prompt, save_path)
    
    # If LLM API key is provided, perform LLM analysis
    if llm_api_key:
        print("Performing LLM analysis...")
        try:
            analysis = await analyze_with_llm(prompt, llm_api_key)
            
            # Append the analysis to the file
            with open(save_path, 'a') as f:
                f.write("\n\n--- LLM Analysis ---\n")
                f.write(analysis)
            
            return prompt, f"Data, instructions, and LLM analysis saved to {save_path}"
        except Exception as e:
            return prompt, f"Data and instructions saved, but LLM analysis failed: {str(e)}"
    
    return prompt, f"Data and instructions saved to {save_path}"

# Update the main block to properly handle async execution
if __name__ == "__main__":
    # Get and validate ticker input
    while True:
        ticker = input("Enter company ticker symbol (e.g., AAPL, TSLA): ").strip().upper()
        if ticker and ticker.isalpha():
            break
        print("Invalid ticker! Please enter a valid stock symbol.")

    # Get and validate fiscal year input
    while True:
        fyear = input("Enter fiscal year for 10-K report (e.g., 2024): ").strip()
        if fyear and fyear.isdigit() and len(fyear) == 4:
            break
        print("Invalid year! Please enter a 4-digit year (e.g., 2024).")

    # Get and validate save path input
    default_path = f"{ticker}_{fyear}_balance_sheet_analysis.txt"
    while True:
        save_path = input(f"Enter save path [default: {default_path}]: ").strip() or default_path
        try:
            with open(save_path, 'a') as f:
                pass
            os.remove(save_path)
            break
        except OSError:
            print(f"Invalid path! Please enter a valid file path.")

    # Get LLM API key
    llm_api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not llm_api_key:
        llm_api_key = input("Enter DeepSeek API key (press Enter to skip LLM analysis): ").strip() or None

    # Execute analysis with validated parametebrs
    try:
        result = asyncio.run(analyze_balance_sheet(ticker, fyear, save_path, llm_api_key))
        print(f"\nAnalysis completed: {result[1]}")
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")