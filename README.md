# YNAB Daily Balance Email Script

A Python script that fetches category balances from YNAB API and emails a formatted HTML report. Perfect for daily budget monitoring and tracking.

## Features

- 📊 **Daily Budget Reports**: Automatically fetch and email your YNAB category balances
- 🎯 **Customizable Categories**: Configure which category groups to include in reports
- 📧 **HTML Email Reports**: Beautiful, formatted HTML emails with transaction history
- 🗂️ **Report Management**: Automatic cleanup of old reports with configurable retention
- 📁 **Flexible Storage**: Save reports to any directory you specify
- 🔄 **Delta Updates**: Efficient API usage with YNAB's delta request feature
- 📈 **Transaction Tracking**: Shows recent approved transactions in tracked categories

## Quick Start

### 1. Prerequisites

- Python 3.7 or higher
- YNAB account with API access
- Email account (Gmail, Outlook, etc.)

### 2. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd ynab-daily-reports

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings:
   ```env
   # YNAB API Configuration
   YNAB_API_TOKEN=your_ynab_api_token_here
   BUDGET_ID=your_budget_id_here

   # Email Configuration
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USER=your_email@gmail.com
   EMAIL_PASS=your_app_password
   TO_EMAIL=recipient@example.com

   # Report Configuration
   INCLUDED_GROUPS=Essential,Medical,Non-Essential,Quality of Life,Wishful Savings
   REPORT_PATH=c:/users/Patrick/YNAB Reports
   RETAIN_REPORT_DAYS=30
   ```

### 4. Get Your YNAB API Token

1. Go to [YNAB Developer Settings](https://app.youneedabudget.com/settings/developer)
2. Click "New Token"
3. Copy the token to your `.env` file

### 5. Get Your Budget ID

1. Go to your YNAB budget
2. Look at the URL: `https://app.youneedabudget.com/budget/your-budget-id`
3. Copy the budget ID to your `.env` file

### 6. Test the Setup

```bash
# Test SMTP connection
python PYnab.py --test-smtp

# Run the script
python PYnab.py
```

## Configuration Options

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `YNAB_API_TOKEN` | ✅ | - | Your YNAB API token |
| `BUDGET_ID` | ✅ | - | Your YNAB budget ID |
| `EMAIL_HOST` | ✅ | - | SMTP server hostname |
| `EMAIL_PORT` | ❌ | 587 | SMTP server port |
| `EMAIL_USER` | ✅ | - | Your email username |
| `EMAIL_PASS` | ✅ | - | Your email password/app password |
| `TO_EMAIL` | ✅ | - | Recipient email(s), comma-separated |
| `INCLUDED_GROUPS` | ✅ | - | Category groups to include, comma-separated |
| `REPORT_PATH` | ❌ | Script directory | Directory to save HTML reports |
| `RETAIN_REPORT_DAYS` | ❌ | 30 | Days to keep old reports |

### Multiple Recipients

To send reports to multiple people, use comma-separated email addresses:

```env
TO_EMAIL=patrick@example.com,jane@example.com,spouse@example.com
```

### Windows Paths

For Windows paths, use forward slashes:

```env
REPORT_PATH=c:/users/Patrick/YNAB Reports
```

## Scheduling

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to "Daily" at your preferred time
4. Set action to start program: `python.exe`
5. Add arguments: `C:\path\to\PYnab.py`
6. Set start in: `C:\path\to\script\directory`

### Linux/macOS Cron

Add to your crontab (`crontab -e`):

```bash
# Daily at 8 AM
0 8 * * * /usr/bin/python3 /path/to/PYnab.py
```

## Report Features

### HTML Email Report Includes:

- **Budget Summary**: Credit card debt and negative balances
- **Recent Transactions**: Approved transactions in tracked categories
- **Category Balances**: Available, budgeted, and activity amounts
- **Summary Statistics**: Total available balance and category counts

### Report Storage:

- HTML reports saved with timestamps
- Automatic cleanup of old reports
- Configurable retention period
- Customizable storage location

## Troubleshooting

### Common Issues

1. **SMTP Authentication Error**
   - Use app passwords for Gmail/Outlook
   - Enable 2-factor authentication first

2. **YNAB API Errors**
   - Verify your API token is correct
   - Check that your budget ID is valid

3. **File Permission Errors**
   - Ensure the report directory exists and is writable
   - Check file permissions on Windows

### Testing

```bash
# Test SMTP connection only
python PYnab.py --test-smtp

# Check logs
tail -f ynab_email.log
```

## Security Notes

- Never commit your `.env` file to version control
- Use app passwords instead of your main email password
- Keep your YNAB API token secure
- Consider using environment variables in production

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is open source. Feel free to modify and distribute as needed.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs in `ynab_email.log`
3. Open an issue on GitHub
