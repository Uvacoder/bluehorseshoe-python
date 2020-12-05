from scraper import get_contracts, update_months
from optionparser import *
from dividendscraper import get_dividends
from settings import get_setting, set_setting, read_settings, save_settings, print_settings, is_setting
from csv import reader, writer
from enum import Flag, auto
import re
import sys
import datetime
from os import path, makedirs

# TODO: Calendar support

lists = dict()
symbols = set()
_types = [ "put", "call" ]

symbol_month = dict() 
month_csv_modified = False
symbol_csv_modified = False
setting_csv_modified = False

DATA_DIR = "data/"
MONTHS_CSV = DATA_DIR + "months.csv"
SYMBOL_CSV = DATA_DIR + "symbols.csv"
SETTINGS_CSV = DATA_DIR + "settings.csv"

pattern = re.compile("\s+|\s*,\s*")

today = datetime.date.today()

class Mode(Flag):
	SPREADS = auto()
	OPTIONS = auto()
	CALENDAR = auto()

# LIST MANIPLUATION

def remove_symbols(interest_list, symbols):
	for s in symbols:
		s = s.strip("$").upper()
		if s: # Ignore empty strings
			if s in interest_list:
				interest_list.remove(s)
			else:
				print(s + " not in list")
		
def add_symbols(interest_list, symbols):
	for s in symbols:
		s = s.strip("$").upper()
		if (s): # Ignore empty strings
			interest_list.add(s)

# OUTPUT

def print_spreads(type, spreads):
	type = type.lower()
	# TODO: Should reverse order for calls
	for spread in spreads:
		print("%.2f/%.2f %s: $%.2f/%.1f%% \t(%d%%; %.1f%% out)" % (spread[0], spread[1], type, spread[4], spread[5] * 100, spread[6], spread[7] * 100))
	print("") # Newline
	
def print_options(type, price, options):
	type = type.lower()
	if type == "put":
		for opt in options:
			if (opt[0] > price): print("-", end='')
			print("%.2f %s: %.2f/%.1f%% \t(%d%%; %.1f%% out) %.2f if put" % (opt[0], type, opt[1], opt[3], opt[4], opt[5] * 100, opt[6]))
	elif type == "call":
		for opt in options:
			if (opt[0] < price): print("-", end='')
			print("%.2f %s: %.2f/%.1f%% \t(%d%%; %.1f%% out) %.1f%% if called" % (opt[0], type, opt[1], opt[3], opt[4], opt[5] * 100, opt[6] * 100))
	print("") # Newline
	
def print_list(name):
	if name in lists.keys():
		print("%s: %s" % (name, ", ".join(lists[name]))) 
	else:
		print("%s is not a valid list" % name)
		
def print_dividends(dividends):
	for d in dividends:
		print("%s (%s): %s %.2f/%.2f (%.2f%%)" % (d[1], d[0], d[2], d[3], d[4], d[5] * 100))
	print("") # Newline

def print_invalid_error(ticker):
	err_string = "| %s is not a valid stock ticker |" % ticker.upper()
	line_string = " " + "-" * (len(err_string) - 2)
	print(line_string)
	print(err_string)
	print(line_string, "\n")

def print_help():
	print("""Available commands:
	help				Print available commands
	options [$STOCKS, LISTS]	Fetch and print options for all tickers or lists provided as arguments.
						If no arguments are provided, fetch all lists.
	spreads [$STOCKS, LISTS]	Fetch and print option spreads for all tickers or lists provided as arguments. 
						If no arguments are provided, fetch all lists.
	calendar [$STOCKS, LISTS]	Fetch and print calendar spreads for all tickers or lists provided as arguments.
						If no arguments are provided, fetch all lists.
	fetch [$STOCKS, LISTS]		Fetch and print options, spreads, and calendar spreads for all tickers or lists provided as arguments. 
						If no arguments are provided, fetch all lists.
	[$STOCKS]			Same as fetch [$STOCKS]. The first stock must start with a $
	create [LISTS]			Create a new list for each of the provided argument, if no list exists. Lists are case-sensitive.
	refresh				Refresh contract months for all tickers in all lists
	add LIST [$STOCKS]		Add all tickers from $STOCKS to LIST. Lists may not contain duplicates
	delete LIST [$STOCKS]		Delete all tickers from $STOCKS from LIST if present
	list [LISTS]			Print the contents of all lists from LISTS. If no lists are provided, print the contents of all lists.
	list_months			Print the front contract month for all tickers in any list
	dividends			List stocks with ex-dividend days tomorrow
	settings			List all settings and current values
	set SETTING VALUE		Set SETTING to VALUE, if SETTING is a valid setting (i.e. listed under 'settings')
	save				Save lists, months, and settings to persistent storage
	exit or quit			Exit the program
		
	For commands which take multiple arguments of the same type (e.g. options, spreads, fetch, create, list), arguments may be separated by commas or spaces.""")


"""Tickers can be separated by spaces or commas, upper or lowercase, and may appear with or without a leading $. Lists are case sensitive. To get a ticker with the same name as one of your lists, change the case of the ticker or prefix it with a $. All arguments prefixed with $ are treated as tickers."""

# PERSISTENT DATA

def save_months():
	# Store to dictionary on disk
	w = writer(open(MONTHS_CSV, "w", newline=''))
	for key, val in symbol_month.items():
		w.writerow([key] + val)
		
def save_lists():
	# Store to dictionary on disk
	w = writer(open(SYMBOL_CSV, "w", newline=''))
	for key, val in lists.items():
		w.writerow([key] + list(val))

# SCRAPING METHODS

def fetch_multiple(symbols, instruments, no_lists=False):
	global month_csv_modified
	for symbol in symbols:
	
		# Indirect lists
		if not no_lists and not symbol[0] == "$" and symbol in lists.keys():
			fetch_multiple(lists[symbol], instruments, True)
			continue
			
		symbol = symbol.strip("$")
		if not symbol:
			continue
	
		# Get months if absent
		if symbol not in symbol_month.keys():
			if update_months(symbol, symbol_month):
				month_csv_modified = True
			else:
				print_invalid_error(symbol)
				continue
			
		# Make sure the date is more than MIN_TIME_DIFFERENCE away
		month = symbol_month[symbol][0]
		if (datetime.datetime.strptime(month, "%Y%m%d").date() - today < datetime.timedelta(get_setting("MIN_TIME_DIFFERENCE"))):
			month = symbol_month[symbol][1]
			symbol_month[symbol] = symbol_month[symbol][1:]
			month_csv_modified = True
			
		for type in _types:

			(price, options) = get_contracts(symbol, month, type) # Prints url and header
			print("") # New line
			
			if (instruments & Mode.OPTIONS):
				filtered_options = filter_options(type, price, options)
				
				if (filtered_options):
					print("--%s options--" % type.capitalize())
					print_options(type, price, filtered_options)
				else:
					print("No %s options\n" % type.capitalize())
			
			if (instruments & Mode.SPREADS):
				cred_spreads = credit_spreads(price, type, options, not get_setting("PRINT_ALL"))
				
				if (cred_spreads):
					print("--%s spreads--" % type.capitalize())
					print_spreads(type, cred_spreads)
				else:
					print("No %s spreads\n" % type.capitalize())
			
			if (instruments & Mode.CALENDAR):
				print("Calendar spreads not implemented yet\n")


def parse(cmd):
	global month_csv_modified
	global symbol_csv_modified
	global setting_csv_modified
	if cmd.strip() == "refresh":
		print("Refreshing contract months...")
		# Get the next contract for each symbol
		for symbol in symbols:
			if not update_months(symbol, symbol_month):
				print_invalid_error(symbol)
			
		month_csv_modified = True
	elif cmd.startswith("spreads"):
		symbols_list = [s for s in pattern.split(cmd[7:]) if s.strip("$")]
		# If no symbols, default to all (split will return [] in this case)
		if not symbols_list:
			symbols_list = lists.keys()
		fetch_multiple(symbols_list, Mode.SPREADS)
	elif cmd.startswith("options"):
		symbols_list = [s for s in pattern.split(cmd[7:]) if s.strip("$")]
		if not symbols_list:
			symbols_list = lists.keys()
		fetch_multiple(symbols_list, Mode.OPTIONS)
	elif cmd.startswith("calendar"):
		symbols_list = [s for s in pattern.split(cmd[8:]) if s.strip("$")]
		if not symbols_list:
			symbols_list = lists.keys()
		fetch_multiple(symbols_list, Mode.CALENDAR)
	elif cmd.startswith("fetch"):
		symbols_list = [s for s in pattern.split(cmd[5:]) if s.strip("$")]
		if not symbols_list:
			symbols_list = lists.keys()
		fetch_multiple(symbols_list, Mode.SPREADS | Mode.OPTIONS | Mode.CALENDAR)
	elif cmd.startswith("$"): # Assume fetch command if only symbols are given
		symbols_list = [s for s in pattern.split(cmd) if s.strip("$")]
		if not symbols_list:
			symbols_list = lists.keys()
		fetch_multiple(symbols_list, Mode.SPREADS | Mode.OPTIONS | Mode.CALENDAR)
	elif cmd.startswith("add"):
		l = [s for s in pattern.split(cmd[4:]) if s.strip("$")]
		if not l or l[0] not in lists.keys():
			print("No valid list specified")
		else:
			add_symbols(lists[l[0]], l[1:])
			symbol_csv_modified = True
			print_list(l[0])
	elif cmd.startswith("remove"): 
		l = [s for s in pattern.split(cmd[7:]) if s.strip("$")]
		if not l or l[0] not in lists.keys():
			print("No valid list specified")
		else:
			remove_symbols(lists[l[0]], l[1:])
			symbol_csv_modified = True
			print_list(l[0])
	elif cmd.startswith("list"):
		plists = [ s for s in pattern.split(cmd[5:]) if s]
		# If no lists, default to all (split will return [] in this case)
		if not plists:
			plists = lists.keys()
		for plist in plists:
			if plist in lists.keys():
				print_list(plist)
			else:
				print("%s is not a valid list" % plist)
	elif cmd.startswith("create"):
		for s in pattern.split(cmd[7:]):
			s = s.strip("$")
			if (s):
				if s not in lists.keys():
					lists[s] = set()
					symbol_csv_modified = True
				else:
					print("%s already exists" % s)
			else:
				print("No list specified")
	elif cmd.startswith("delete"):
		for s in pattern.split(cmd[7:]):
			if (s):
				if s in lists.keys():
					ans = ""
					# Delete empty lists by default
					if not lists[s]:
						ans = "y"
					else:
						print_list(s)
					# Ask for confirmation
					while (ans != "n" and ans != "y"):
						ans = input("%s is is not empty. Are you sure? y/n: " % s).lower()
						
					if ans == "y":
						del lists[s]
						symbol_csv_modified = True
				else:
					print("%s does not exist" % s)
			else:
				print("No list specified")
	elif cmd.strip() == "list_months": # TODO: Split up by list
		for s in symbols:
			print("%s: %s" % (s, symbol_month[s][0]))
	elif cmd.startswith("dividends"):
		args = [s for s in pattern.split(cmd[9:]) if s]
		if (args and args[0].isdigit()):
			print_dividends(get_dividends()[:int(args[0])])
		else:
			print_dividends(get_dividends())
	elif cmd.strip() == "settings":
		print_settings()
	elif cmd.startswith("set "):
		args = [s for s in pattern.split(cmd[4:]) if s]
		if len(args) != 2:
			print("Requires both key and value")
		elif is_setting(args[0]):
			set_setting(args[0], args[1])
			save_settings(SETTINGS_CSV) # Save immediately, we don't want to risk a crash erasing settings
		else:
			print("%s is not a valid setting" % args[0])
	elif cmd.strip() == "save":
		save_months()
		save_lists()
		save_settings(SETTINGS_CSV)
	elif cmd.strip() == "help":
		print_help() # TODO: Second level help text for specific commands
	else:
		print("Unknown command: " + cmd);


if __name__ == "__main__":
	# Check for data dir
	if not path.exists(DATA_DIR):
		print("Building data dir")
		makedirs(DATA_DIR)
		
		
	read_settings(SETTINGS_CSV) # Read settings first to get SLOGIN, otherwise getting contract months will fail

	# Load symbols of interest
	if path.exists(SYMBOL_CSV):
		r = reader(open(SYMBOL_CSV, "r", newline=''))
		for row in r:
			lists[row[0]] = set(row[1:])
			symbols.update(row[1:])

	# Load up the front contract for each symbol (fetch if absent)
	if not path.exists(MONTHS_CSV):
		print("Refreshing contract months...")
		# Fetch the next contract for each symbol
		for symbol in symbols:
			if not update_months(symbol, symbol_month):
				print_invalid_error(symbol)
				# Remove symbol from lists automatically?
		# Save immediately
		save_months()
	else:
		# Load from stored dictionary
		r = reader(open(MONTHS_CSV, "r", newline=''))
		for row in r:
			if (len(row) < 2):
				# If there are no months, retry getting them
				if update_months(row[0], symbol_month):
					month_csv_modified = True
				else:
					print_invalid_error(symbol)
			else:
				symbol_month[row[0]] = row[1:]
		for symbol in symbols:
			if symbol not in symbol_month.keys() or not symbol_month[symbol]:
				if update_months(symbol, symbol_month):
					month_csv_modified = True
				else:
					print_invalid_error(symbol)
	
	if not get_setting("SLOGIN"):
		print("SLOGIN not set for options. Use 'set SLOGIN xxxxxxxxxx' to set.")
	
	running = True
	
	# Non-interactive mode
	if len(sys.argv) > 1:
		parse(" ".join(sys.argv[1:]))
		running = False
		
	# Main loop
	while (running):
		cmd = input("opt>")
		if cmd == "exit" or cmd == "quit":
			running = False;
			print("quitting...")
		else:
			parse(cmd)
		

	# Shutdown procedures
	

	# Write if modified
	if (month_csv_modified):
		save_months()
			
	if (symbol_csv_modified):
		save_lists()
	
	if (setting_csv_modified):
		save_settings(SETTINGS_CSV)