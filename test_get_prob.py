from datetime import datetime, timezone, timedelta
from tradfi import get_tradfi_implied_probability, extract_financial_target

q1 = "US national Bitcoin reserve before 2027?"
print(extract_financial_target(q1))
