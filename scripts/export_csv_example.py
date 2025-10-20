
from utils.csv_tools import export_reminders_csv
export_reminders_csv('data/pillbot.db', 'data/reminders_export.csv')
print('Exported to data/reminders_export.csv')
