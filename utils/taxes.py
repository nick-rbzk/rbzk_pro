

def self_employ_tax(income):
    """ 
    Rate: 15.3% of 92.35% of your net profit. 
    This covers your contributions to Social Security 
    ($40,000 * 92.35% * 15.3%),
    """
    return income * (92.35 / 100) * (15.3 / 100)

def federal_income_tax(income):
    """ This is an aproximate extimate."""
    return income * (7.5 / 100)