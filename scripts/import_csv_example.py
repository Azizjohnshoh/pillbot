
from utils.csv_tools import import_reminders_csv
import sys
infile = sys.argv[1] if len(sys.argv)>1 else 'data/reminders_import.csv'
import_reminders_csv('data/pillbot.db', infile)
print('Imported', infile)
