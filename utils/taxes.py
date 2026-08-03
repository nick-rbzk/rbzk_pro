

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


def total_taxes(job):
    income = float(job.job_income()) 
    self_employ_owed = self_employ_tax(income)
    federal_owed = federal_income_tax(income)
    total = self_employ_owed + federal_owed
    total =  '{0:.2f}'.format(total)
    return f"{total}$"

def income_after_tax(job):
    income = float(job.job_income())
    self_employ_owed = self_employ_tax(income)
    federal_owed = federal_income_tax(income)
    after_tax = income - (self_employ_owed + federal_owed)
    return '{0:.2f}'.format(after_tax)