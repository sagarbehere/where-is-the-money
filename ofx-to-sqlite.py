# This script is called like: python3 ofx-to-sqlite.py foo.ofx path/to/sqlite-database.db
# foo.ofx is the file downloaded by ofxtools (or manually) from the institution's website
# sqlite-database.db is a sqlite database file with a particular structure.
# Open up the provided sqlite.db file in e.g. sqlitestudio to explore it

import argparse
from ofxparse import OfxParser
import codecs
import datetime
import dateutil.parser as dparser
import sqlite3

def parseargs():
	parser = argparse.ArgumentParser()
	parser.add_argument('ofxfile', help="Input OFX/QFX file. Expected to have extension .ofx or .qfx")
	parser.add_argument('sqlitedbfile', help="SQLite database. Expected to have extention .db")
	args = parser.parse_args()	
	return(args.ofxfile,args.sqlitedbfile)

# TODO: Add error checking to this function
def open_ofx_file(ofxfilename):
	with codecs.open(ofxfilename) as fileobj:
		ofx=OfxParser.parse(fileobj)
		# TODO: Verify above function executed successfully?
		return ofx

# TODO: Add error checking to this function
def open_sqlite_db(sqlitedbfilename):
	# TODO: Verify sqlitedbfilename exists?
	dbconn = sqlite3.connect(sqlitedbfilename)
	# TODO: Verify connect is successful?
	return dbconn

def determine_account_name(ofx):
	# TODO: Ensure ofx is a valid object
	# NOTE: Open the OFX file in a text editor to understand the strings used for account.institution.organization. These are just examples from the few ofx files I got my hands on
	accountName = 'Unknown'
	account = ofx.account
	if account.institution.organization == 'AMEX':
		accountName = 'AmexBlueCash'
	elif account.institution.organization == 'B1':
		accountName = 'ChaseSapphireReserve'
	elif account.institution.organization == 'Tech CU' or account.institution.organization == 'TECHCUDC':
		if account.account_type == 'CHECKING':
			accountName = 'TechCUChecking'
		elif account.account_type == 'SAVINGS':
			accountName = 'TechCUSavings'
	elif account.institution.organization == 'Bank of America':
		if account.account_type == 'CHECKING':
			accountName = 'BofAChecking'
		elif account.account_type == 'MONEYMRKT':
			accountName = 'BofASavings'
	return accountName

def get_transactions(ofx):
	# TODO: Ensure ofx is a valid object
	statement = ofx.account.statement
	transactions = statement.transactions
	# Below two lines sort from most recent to least recent
	# TODO: Probably should sort by transactionid rather than date, since there can be multiple transactions on a given date
	transactions.sort(key=lambda trans: trans.date)
	transactions.reverse()
	return transactions

def write_transactions_to_db(transactions, dbconn, account):
	# TODO: ensure all args have valid content, esp. transactions has at least one entry
	dbcursor = dbconn.cursor()
	accountTrans = account+'Trans' # The transactions table for the account
	accountMeta = account+'Meta' # The meta table for the account
	writeCount = 0
	for transaction in transactions:
		# We will only add a transaction if it does not exist in db
		# Existence is determined as: If transid exists within +/- 5 days of trans date
		# Probably not needed, since transaction id is defined as unique in database table
		# accountTrans cols are: TransactionId, DatePosted, Payee, Amount, Memo, Category, Notes
		# accountMeta cols are: TransactionId, DBTimestamp, IsInGSheets
		dateUpper = transaction.date + datetime.timedelta(days=+5)
		dateLower = transaction.date - datetime.timedelta(days=+5)
		dbcursor.execute('''SELECT * FROM '''+accountTrans+''' WHERE date(DatePosted) BETWEEN ? AND ?''', (dateLower.strftime('%Y-%m-%d'), dateUpper.strftime('%Y-%m-%d')))
		exists = 0 # Does transaction exist? Default is no
		for dbrow in dbcursor:
			if dbrow[0] == transaction.id:
				#print (f"Row with transaction id {transaction.id} already exists. Skipping..")
				#print (dbrow)
				exists = 1
				break
		if exists == 0:
			# First add the transaction data. Category should be Unknown and Notes should be blank
			dbcursor.execute('''INSERT INTO '''+accountTrans+'''("TransactionId", "DatePosted", "Payee", "Amount", "Memo", "Category", "Notes") VALUES (?,?,?,?,?,?,?)''', (transaction.id, transaction.date.strftime("%Y-%m-%d"), transaction.payee, str(transaction.amount), transaction.memo, "Unknown", ""))
			# Then the transaction metadata. IsInGSheets should be 0
			dbcursor.execute('''INSERT INTO '''+accountMeta+'''("TransactionId", "DBTimestamp", "IsInGSheets") VALUES (?, ?, ?)''', (transaction.id, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), 0))
			writeCount = writeCount +1
	dbconn.commit()
	return writeCount

def print_ofx_data(ofx):
	# TODO: Ensure ofx is valid object
	# Print ofx stats: accountBalance + asOf, stmtStart, stmtEnd
	accountBalance = ofx.account.statement.balance
	balanceAsOf = ofx.account.statement.balance_date.strftime('%Y-%m-%d')
	stmtStartDate = ofx.account.statement.start_date.strftime('%Y-%m-%d')
	stmtEndDate = ofx.account.statement.end_date.strftime('%Y-%m-%d')
	print(f'Account balance: {accountBalance} as of {balanceAsOf}')
	print(f'Statement start date: {stmtStartDate}')
	print(f'Statement end date: {stmtEndDate}')

def main():
	(ofxfilename, sqlitedbfilename) = parseargs()
	ofx = open_ofx_file(ofxfilename)
	dbconn = open_sqlite_db(sqlitedbfilename)
	# TODO: Check that ofx, dbconn are not None or Null or similar
	account = determine_account_name(ofx)
	if account == 'Unknown':
		print ("Unknown account/institution/organization ", ofx.account.institution.organization, "Exiting..")
		quit() # TODO: clean up ofx and dbconn. Prolly need to close them cleanly. Try Finally?
	print(f'Detected account: {account}')
	print_ofx_data(ofx)
	transactions = get_transactions(ofx)
	print(f'Found {len(transactions)} transactions.')
	# TODO: Ensure that transactions has at least one transaction
	nTransactions_written = write_transactions_to_db(transactions, dbconn, account)
	print (f'{nTransactions_written} transactions written to database')
	dbconn.close()
	# TODO: Should probably close ofx cleanly.

if __name__ == "__main__":
    main()
