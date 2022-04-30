# This script is called as: python3 autocategorize.py path/to/sqlite-database.db FinancialAccountName
# FinancialAccountName is one of valid_accounts from the verify_accounts() function below
# To really understand how this autocategorizer works, read the reddit comment mentioned below. It shows how it works in <10 lines of code. It's very easy, I promise! :)
# The rest of the code in this script is merely to feed data to and get data out of the autocategorizer

# https://stackabuse.com/text-classification-with-python-and-scikit-learn/
# https://towardsdatascience.com/pandas-dataframe-playing-with-csv-files-944225d19ff?gi=8fce15d7d81d
# https://towardsdatascience.com/pandas-dataframe-a-lightweight-intro-680e3a212b96
# https://www.reddit.com/r/learnpython/comments/8ickh7/grouping_bank_transactions_with_text_analysis/dyr7u67/

# On MacOS, you may need to install/configure some packages as follows

# pip install pandas
# pip install cython
# brew install xz
# brew install libomp
# Add following to .bashrc or .zshrc

#export CC=/usr/bin/clang
#export CXX=/usr/bin/clang++
#export CPPFLAGS="$CPPFLAGS -Xpreprocessor -fopenmp"
#export CFLAGS="$CFLAGS -I/usr/local/opt/libomp/include"
#export CXXFLAGS="$CXXFLAGS -I/usr/local/opt/libomp/include"
#export LDFLAGS="$LDFLAGS -Wl,-rpath,/usr/local/opt/libomp/lib -L/usr/local/opt/libomp/lib -lomp"

# pip install scikit-learn

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier

import re
import argparse
import sqlite3
from prompt_toolkit import prompt
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.validation import Validator, ValidationError

def preprocess_description(description):
	# Remove all special characters
	document = re.sub(r'\W', ' ', description)
	# Remove all words containing numbers
	document = re.sub(r'\w*\d\w*', '', document).strip()
	# Remove all single characters
	document = re.sub(r"\b[a-zA-Z]\b", '', document)
	# Alt. remove all single chars
	document = re.sub(r'\s+[a-zA-Z]\s+', ' ', document)
	# Remove all single chars from start
	document = re.sub(r'\^[a-zA-Z]\s+', ' ', document)
	# Substitute multiple spaces with single space
	document = re.sub(r'\s+', ' ', document, flags=re.I)
	# Convert string to lower case
	document = document.lower()
	# Remove "aplpay" and "com" (for .com) from string
	document = document.replace('aplpay ', '')
	document = document.replace('com', '')
	return document

def fetch_training_data(dbconn, account, trainingfile):
	df = pd.DataFrame() # This will hold the Description,Categories that will train the classifier
	dbcursor = dbconn.cursor()
	if trainingfile: # i.e. if trainingfile is not None, use that as source of training data
		# This is a csv file with Description and Category columns
		print (f'Using training file {trainingfile} for training.')
		df = pd.read_csv(trainingfile) # TODO: Error checking
		
		df['Description'] = df.Description
		df['Category'] = df.Category
		if len(df) < 1:
			print(f'Trainingfile seems to be empty. Stopping..')
			quit()
	elif trainingfile == None: # Load pre-categorized transactions in db as training data
		institution = account+'Trans' # See sqlite db structure. Basically db column names are either account+'Trans' for transactions or account+'Meta' for metadata
		dbcursor.execute('''SELECT Payee,Memo,Category FROM '''+institution+''' WHERE Category != 'Unknown' ''')
		raw_training_records = dbcursor.fetchall() # FIXME: Can blow up with memory issues if there are too many records
		if len(raw_training_records) < 1:
			print ("Hmm... seems like there are no categorized records available for training. Quitting.")
			quit()
		nTrainingTransactions = len(raw_training_records)
		print (f"Using {nTrainingTransactions} previously categorized transactions for training.")
		training_description = []
		training_categories = []
		for row in raw_training_records:
			training_description.append(row[0]+' '+row[1]) # training description is combination of payee and memo
			training_categories.append(row[2])
		df['Description'] = training_description
		df['Category'] = training_categories
		
	return df

def get_trained_classifier(df):
	# TODO: Check that df is not NULL etc. df['Description'] should have training descriptions. df['Category'] should have corresponding categories for training
	# First, we need to pre-process the descriptions. See documentation comments of preprocess_description() for more
	df['ProcessedDescription'] = [preprocess_description(x) for x in df.Description] # Hmm.. seems like df['Description'] and df.Description are equivalent??
	tfidf=TfidfVectorizer()
	x_train = tfidf.fit_transform(df['ProcessedDescription'])
	le = LabelEncoder()
	y_train = le.fit_transform(df['Category'])
	classifier = RandomForestClassifier(n_jobs=-1, n_estimators=100)
	classifier.fit(x_train.todense(), y_train)
	
	return(classifier, tfidf, le)
	
def get_uncategorized_transactions(dbconn, account):
	dbcursor = dbconn.cursor()
	institution = account+'Trans'
	dbcursor.execute('''SELECT TransactionId,Payee, Memo, Amount FROM '''+institution+''' WHERE Category = 'Unknown' ''')
	uncategorized_records = dbcursor.fetchall() # FIXME: Can blow up with memory issues if there are too many records
	return uncategorized_records

def categorize_transactions(classifier, tfidf, le, uncategorized_transactions):
	uncategorized_transids = []
	uncategorized_descs = []
	#uncategorized_amounts = []

	for row in uncategorized_transactions: # TransactionId,Payee,Memo,Amount
		uncategorized_transids.append(row[0])
		uncategorized_descs.append(row[1]+' '+row[2]) # descs == payee + memo
		#uncategorized_amounts.append(row[3]) # Not sure this is actually needed in this function

	descs_to_categorize = [preprocess_description(x) for x in uncategorized_descs]
	x_predict = tfidf.transform(descs_to_categorize)
	predicted = classifier.predict(x_predict.todense())
	guessed_categories = le.inverse_transform(predicted)
	return guessed_categories

def get_valid_categories(dbconn):
	dbcursor = dbconn.cursor()
	dbcursor.execute('''SELECT Category FROM Categories''')
	valid_categories_tuple = dbcursor.fetchall()

	valid_categories = []
	for cat in valid_categories_tuple:
		valid_categories.append(cat[0])
	return valid_categories

# An interactive function
def verify_categories_and_add_notes(dbconn, uncategorized_transactions, guessed_categories):
	valid_categories = get_valid_categories(dbconn)
	true_categories = guessed_categories
	category_completer = FuzzyWordCompleter(valid_categories)
	
	def is_valid_category(text):
		if text in valid_categories:
			return True
		elif text == 'q':
			return True
		elif text == '': #User pressed enter key
			return True
		else:
			return False

	CategoryValidator = Validator.from_callable(
		is_valid_category,
		error_message='Invalid category',
		move_cursor_to_end=True)

	notes = [''] * len(guessed_categories) # Place holder list for any notes that may need to be added
	for i in range(len(guessed_categories)):
		# Need to prompt user whether the category was correct. If not, user should enter the correct category
		# user entered category must be validated to be in the master Category list, else polite error msg
		# user entered category must overwrite guessed category
		
		true_category = prompt(f'{uncategorized_transactions[i]} --> {guessed_categories[i]} . [Enter] to accept, q to quit, or type correct category:', completer=category_completer, validator=CategoryValidator)
		if true_category == 'q':
			break
		elif true_category:
			true_categories[i] = true_category
			#print(f'True category is {true_category}')
		note = prompt(f'Add note? :')
		if note:
			notes[i] = note
	return (true_categories, notes)

def write_verified_categories_to_db(dbconn, account, uncategorized_transactions, verified_categories, notes):
	dbcursor = dbconn.cursor()
	# A brief sanity check
	if len(uncategorized_transactions) != len(verified_categories):
		print (f'Something is VERY WRONG: Length of uncategorized_transactions != Length of verified_categories. ABORTING!')
		quit()
	if len(notes) != len(verified_categories):
		print (f'Something is VERY WRONG: Length of notes != Length of verified_categories. ABORTING!')
		quit()
	
	institution = account+'Trans'
	for i in range(len(verified_categories)):
		# uncategorized_transactions[i] should be the i'th row and each row is TransactionId,Payee,Memo,Amount
		dbcursor.execute('''UPDATE '''+institution+''' SET Category = ?, Notes = ? WHERE "TransactionId" = ?''', (verified_categories[i], notes[i], uncategorized_transactions[i][0]))

	dbconn.commit()

def auto_categorize(dbconn, account, trainingfilename):
	# Decide whether to use training file or pre-categorized transactions
	# Load up the training data and train the classifier
	# Load up the Uncategorized transactions in account and categorize them
	# Do interactive check of categorization along with additional Notes
	
	df = fetch_training_data(dbconn, account, trainingfilename) # Remember: The training descriptions returned are not pre-processed for training
	# TODO: Ensure that df is not NULL etc.
	(classifier, tfidf, le) = get_trained_classifier(df)
	uncategorized_transactions = get_uncategorized_transactions(dbconn, account) # Will return TransactionId,Payee,Memo,Amount of uncategorized transactions
	if len(uncategorized_transactions) < 1:
		print(f'There seem to be no uncategorized transactions in {account}. Stopping..')
		quit()
	guessed_categories = categorize_transactions(classifier, tfidf, le, uncategorized_transactions) # same length as uncategorized_transactions
	(verified_categories, notes) = verify_categories_and_add_notes(dbconn, uncategorized_transactions, guessed_categories)
	write_verified_categories_to_db(dbconn, account, uncategorized_transactions, verified_categories, notes)
	

def parseargs():
	parser = argparse.ArgumentParser()
	parser.add_argument('sqlitedbfile', help="SQLite database. Expected to have extention .db")
	parser.add_argument('account', help="Name of the institution whose transactions should be categorized")
	parser.add_argument('-t', '--trainingfile', default=None, help="Name of input csv file with Description,Category cols used for training")
	args = parser.parse_args()
	return(args.sqlitedbfile, args.account, args.trainingfile)

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

def main():
	(sqlitedbfilename, account, trainingfilename) = parseargs()
	if verify_account(account) == False:
		print(f'Unknown account: {account}. Stopping..')
		quit()
	dbconn = open_sqlite_db(sqlitedbfilename)
	# TODO: Error checking of auto_categorize() below
	# If trainingfilename is valid, auto_categorize() will use its content for training. Else it'll use already categorized transactions in account for training
	auto_categorize(dbconn, account, trainingfilename)
	dbconn.close()

if __name__ == "__main__":
    main()

