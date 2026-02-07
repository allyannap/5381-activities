# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# API Name:
# U.S. Census Bureau – American Community Survey (ACS) 5-Year Estimates (2024)
#
# Documentation:
# https://www.census.gov/data/developers/data-sets/acs-5year.html
# https://www.census.gov/programs-surveys/acs/technical-documentation.html 
#
# Endpoint: 
# https://api.census.gov/data/2024/acs/acs5
#
# Purpose: 
# This script queries nationwide (all U.S. states + DC + PR) demographic data related to citizenship status. 
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

# Load requests library
import os
import requests
from dotenv import load_dotenv

# Loading API key from files 
load_dotenv()

API_KEY = os.getenv("CENSUS_API_KEY")

# Base Census API URL
# the 5-year-plan: the most accurate (out of acs1, acs3, acs5)
url = "https://api.census.gov/data/2024/acs/acs5" 

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# Query parameters: 
params = {
    # get: Total Population (must always be grabbed), everything else
     "get": (
        "NAME,"            # State name 
        "B01001_001E,"     # Total population
        "B05001_002E,"     # U.S. citizen, born in the United States
        "B05001_003E,"     # U.S. citizen, born in Puerto Rico or U.S. Island Areas
        "B05001_004E,"     # U.S. citizen, born abroad of American parent(s)
        "B05001_005E,"     # Naturalized U.S. citizen
        "B05001_006E"      # Not a U.S. citizen
    ),
    # know for ALL states
    "for": "state:*",
    "key": API_KEY
}

# B05001_001E	Estimate!!Total:
# B05001_002E	Estimate!!Total:!!U.S. citizen, born in the United States
# B05001_003E	Estimate!!Total:!!U.S. citizen, born in Puerto Rico or U.S. Island Areas
# B05001_004E	Estimate!!Total:!!U.S. citizen, born abroad of American parent(s)
# B05001_005E	Estimate!!Total:!!U.S. citizen by naturalization
# B05001_006E	Estimate!!Total:!!Not a U.S. citizen
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
response = requests.get(url, params=params)

# Printing status code to verify request success
print("Status code:", response.status_code)  # should be 200

print("Response JSON:")

# Expected response: 
    # For every state, output the (number of):
        # total population
        # native-born citizens
        # citizens born in PR or U.S. Island areas
        # citizens born abroad of American parents
        # naturalized citizens 
        # non-U.S. citizens

print(response.json())

# Expected Data Structure: 
# - JSON array (52x8)
# - Row 0: column headers
# - Rows 1–52: one row per state
#
# Number of Rows:
# - 50 states + DC + Puerto Rico = 52 rows
#
# Number of Columns: 8
# - State Name
# - Total population
# - Native-born citizens
# - U.S. citizens born in PR or U.S. Island areas
# - U.S. citizens born abroad from American parent(s)
# - Naturalized citizens
# - Non-U.S. citizens
# - Number representing state according to U.S. Census documentation


# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# Other ideas:
# Moved from elsewhere; Moved from Abroad; Naturalized U.S. Citizen; Not a U.S. Citizen; Foreign born