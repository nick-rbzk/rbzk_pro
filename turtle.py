import math


def manage_risk(portfolio_size, risk_percentage, N_atr, risk_multiplier, current_comod_price):
	account_risk = (risk_percentage / 100) * portfolio_size

	# N_atr or N can also be called volatility
	# In this case it volatility * current_stock_price
	risk = N_atr * current_comod_price 

	# contract_risk can also be called N dollar value
	contract_risk = risk * risk_multiplier

	num_of_contract_to_purchase = math.floor(account_risk / contract_risk)
	print("Account Risk :", account_risk)
	print("Risk percentage :", risk)
	print("Contract Risk :", contract_risk)
	print("Num contracts to buy :", num_of_contract_to_purchase)




print("_______________Swiss Frank Example_______________")
manage_risk(150_000, 1.5, 4, 2, 100)

print("_________Mini Corn Example______________________")
manage_risk(25_000, 2, 7, 3, 10)

print("_______________________________")
manage_risk(100_000, 2, 7, 2, 50)

print("_________________Live Cattle example________________________")
manage_risk(50_000, 2, 0.80, 2, 400)
# 400 is a price of contract
# 74 is a price of stock
# kinda like price of bitcoin is e.g. 68,750
# price of short or long futures is 347.00


