import os
import requests
from typing import Annotated

class SecReportFetcher:
    """Class for retrieving 10-K reports from Financial Modeling Prep API"""
    
    def __init__(self):
        self.fmp_api_key = os.environ.get("FMP_API_KEY")
        if not self.fmp_api_key:
            raise ValueError("FMP_API_KEY is not set in the environment variables")

    def get_sec_report(
        self,
        ticker_symbol: Annotated[str, "ticker symbol"],
        fyear: Annotated[
            str, 
            "year of the 10-K report, 'yyyy' or 'latest'. Default: 'latest'"
        ] = "latest"
    ) -> str:
        """Retrieve 10-K report URL and filing date"""
        url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker_symbol}?type=10-k&page=0&apikey={self.fmp_api_key}"
        
        response = requests.get(url)
        if response.status_code != 200:
            return f"Failed to retrieve data: {response.status_code}"

        data = response.json()
        filing_url = None
        filing_date = None

        if fyear == "latest":
            filing_url = data[0]["finalLink"]
            filing_date = data[0]["fillingDate"]
        else:
            for filing in data:
                if filing["fillingDate"].split("-")[0] == fyear:
                    filing_url = filing["finalLink"]
                    filing_date = filing["fillingDate"]
                    break

        return f"Link: {filing_url}\nFiling Date: {filing_date}" if filing_url else "No matching report found"