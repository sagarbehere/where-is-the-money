# where-is-the-money
A bunch of scripts to read financial transactions in OFX format, autocategorize them, and upload them to Google sheets

See this blog post for more details: https://sagar.se/blog/where-is-the-money/

The way this works is
1. User gets a set of transactions in OFX format from Financial Institution. Either through ofxget (if financial institution supports it) or manually (most financial institutions allow downloading of statements in ofx format)
2. The ofx-to-sqlite.py script takes each transaction and dumps it into an sqlite database file, which has a couple of tables per finanical account
3. The autocategorize.py file launches an interactive console program that makes a best effort to autocategorize each uncategorized transaction based on previously categorized transactions. You have the option to correct the category if needed and add notes to the transaction. **The more you use this, the more accurate it gets.** In my use case, after manually categorizing the first ~100 transactions, the script correctly guessed subsequent transaction categories most of the time. This is more the case if your transactions are usually from the same merchants you've used before.
4. The sqlite-to-gsheets.py script then uploads all the categorized transactions to a Google Spreadsheet that has a 'Transactions' tab. From there on, you can use Google Sheets magic to create any number/variety of dashboards you want. I usually create a tab for each month to see the transactions for that month in a table and pie charts etc.

NOTES:

- This code is **absolutely terrible**. I barely know any coding/Python and just copy/pasted random code from StackOverflow and the Internet and hacked till it did what I needed. Once that happened, I stopped working on it immediately :D
- You will not be able to use the code/scripts. There's too little information on how to do that. Rather, read it to understand what your own version of these scripts could be like.
- If you have any particular questions about the code or how something works, please ask me (my email is on my website: https://sagar.se ). I'd be happy to shed more light on how it works.
- If enough requests are made, I'll consider brushing up my Python knowledge, updating this code to make it more generically useful and with some more error checking, and documenting it along with usage instructions. 
