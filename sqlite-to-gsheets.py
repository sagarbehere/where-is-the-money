# This script is called as: python3 sqlite-to-gsheets.py path/to/sqlite-database.db FinancialAccountName
# FinancialAccountName is one of valid_accounts in the verify_account() function below

# TODO: Add error checking to all of the the function calls
# FIXME: There is likely nothing here that inserts the transactions in Google Sheets in a most-recent-transaction-first order. Need to reorder transactions in GSheets itself (Menu: Data -> Sort Sheet by Column)
# FIXME: If there is an error uploading to gsheets, the transactions in dB will STILL be marked as uploaded. This is a BUG

# REFERENCES: Read these to understand how this code connects to gsheets and the prep work you need to do in your Google account and what the client_secret.json below does
# https://www.twilio.com/blog/2017/02/an-easy-way-to-read-and-write-to-a-google-spreadsheet-in-python.html
# https://gspread.readthedocs.io/en/latest/oauth2.html

import argparse
import sqlite3
import csv
import datetime
import dateutil.parser as dparser
import time

import gspread
from oauth2client.service_account import ServiceAccountCredentials


def connect_to_google():
	# use creds to create a client to interact with the Google Drive API
	scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
	# Needs the existence of a file in the referred directory, named client_secret.json
	credentials = ServiceAccountCredentials.from_json_keyfile_name('path/to/client_secret.json', scope)
	client = gspread.authorize(credentials)
	return client

def parseargs():
	parser = argparse.ArgumentParser()
	parser.add_argument('sqlitedb', help="Name of sqlite3 database file. Expected to have extension .db")
	parser.add_argument('account', help="Name of the account whose transactions should be sent to gsheets")
	args = parser.parse_args()
	return (args.sqlitedb, args.account)

def verify_account(account):
	valid_accounts = ['AmexBlueCash', 'ChaseSapphireReserve', 'TechCUChecking', 'TechCUSavings', 'BofAChecking', 'BofASavings']
	if account in valid_accounts:
		return True
	else:
		return False

# TODO: Add error checking to this function
def open_sqlite_db(sqlitedbfilename):
	# TODO: Verify sqlitedbfilename exists?
	dbconn = sqlite3.connect(sqlitedbfilename)
	# TODO: Verify connect is successful?
	return dbconn

# CAUTION CAUTION CAUTION
# If the sheet.append_row() function fails for any reason, this entire function gets b0rked and leaves database IsInGSheets in ill-defined state
# ---> There seems to be no way to know if a row was indeed successfully uploaded to GSheets <--- ?? Maybe catch gspread.exceptions.APIError?
# Google Sheets API has a limit of 500 requests per 100 seconds per project, and 100 requests per 100 seconds per user.
# If these limits are exceeded, the append_row() function throws an exception and this prog. halts, leaving some transactions uploaded to GSheets, but for which IsInGSheets remains 0
# Maybe best to wait 100s if numTransactionsUploaded = 99 ??
# Or find some way of batching multiple rows into a single call??
def update_gsheets(dbconn, account, sheet):
	# Find all transactions in db/account for which IsInGSheets = 0
	# Upload that transaction to GSheet
	# Update record for transaction IsInGSheet = 1
	institution = account+'Trans' # See db structure for details
	institutionMeta = account+'Meta' # See db structure for details
	dbcursor = dbconn.cursor()	
	dbcursor.execute('''SELECT COUNT(*) FROM '''+institution+''' INNER JOIN '''+institutionMeta+''' ON '''+institutionMeta+'''.TransactionId = '''+institution+'''.TransactionId WHERE '''+institutionMeta+'''.IsInGSheets = 0''')
	numRows = dbcursor.fetchone() # This is actually a tuple, I think, with numRows[0] being the actual number of rows
	print (f"Found {numRows[0]} transactions which have not been uploaded to Google Sheets.")
	if numRows[0] < 1:
		print(f'There are no un-uploaded transactions. Quitting.')
		quit()
	dbcursor.execute('''SELECT * FROM '''+institution+''' INNER JOIN '''+institutionMeta+''' ON '''+institutionMeta+'''.TransactionId = '''+institution+'''.TransactionId WHERE '''+institutionMeta+'''.IsInGSheets = 0''')
	
	idsToBeUpdated = []

	for count, dbrow in enumerate(dbcursor):
		# dbrow[i] is from Transaction id[0], Date posted[1], Payee[2], Amount[3], Memo[4], Category[5], Notes[6] which needs to be mapped to ofieldnames above which are the cols of the GSheet
		# 
		month = dparser.parse(dbrow[1]).replace(day=1).strftime('%Y-%m-%d')
		# Create a timestamp for when this row is sent to GSheets
		gsheetts = datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S.%f')
		# GSheets headers are: DatePosted, Payee, Category, Amount, Note, Account, Memo, TransactionID, TransactionHash, TransactionMonth, GSheetTimestamp
		GSheetsRow = [dbrow[1], dbrow[2], dbrow[5], dbrow[3], dbrow[6], account, dbrow[4], dbrow[0], '', month, gsheetts]		
		sheet.append_row(GSheetsRow, value_input_option='USER_ENTERED')
		idsToBeUpdated.append(dbrow[0]) # populate transaction ids that need to be marked withIsInGSheets = 1
		if count > 95: # Don't hit GSheets API limit of 100 writes per 100 secs
			print(f'Have uploaded {count+1} transactions. Stopping now to avoid hitting GSheets API limits. Please try again after 100 seconds for remaining transactions.')
			break
		
	for transid in idsToBeUpdated:	
		# That , at the end of (transid,) is important. See: https://stackoverflow.com/questions/16856647/sqlite3-programmingerror-incorrect-number-of-bindings-supplied-the-current-sta
		# The , means that transid is a sequence (tuple in this case) of size 1. Without the , it'll be as if we have supplied strlen(transid) number of bindings
		dbcursor.execute('''UPDATE '''+institutionMeta+''' SET IsInGsheets = 1 WHERE TransactionId = ?''', (transid,))
		
	print (f"Processed {len(idsToBeUpdated)} transactions.")
	
	dbconn.commit()
	
def main():
	# TODO: Error checking for below func
	client = connect_to_google()
	sheet = client.open("Finances").worksheet("Transactions")
	
	(sqlitedbfilename, account) = parseargs()
	if verify_account(account) == False:
		print(f'Unknown account: {account}. Stopping..')
		quit()
		
	dbconn = open_sqlite_db(sqlitedbfilename)
	update_gsheets(dbconn, account, sheet)
	dbconn.close()

if __name__ == "__main__":
    main()
