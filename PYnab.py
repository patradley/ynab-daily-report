#!/usr/bin/env python3
"""
YNAB Daily Balance Email Script

This script fetches category balances from YNAB API and emails a formatted table.
Requires: requests, python-dotenv

Setup:
1. Create a .env file with:
   YNAB_API_TOKEN=your_token_here
   BUDGET_ID=your_budget_id_here
   EMAIL_HOST=your_smtp_host
   EMAIL_PORT=587
   EMAIL_USER=your_email@example.com
   EMAIL_PASS=your_email_password
   TO_EMAIL=recipient@example.com
   INCLUDED_GROUPS=Essential,Medical,Non-Essential,Quality of Life,Wishful Savings
   REPORT_PATH=/path/to/reports/directory
   RETAIN_REPORT_DAYS=30
   
   Note: INCLUDED_GROUPS is a comma-separated list of category group names to include in the report.
   REPORT_PATH specifies where to save HTML reports (defaults to script directory).
   RETAIN_REPORT_DAYS specifies how many days of reports to keep (defaults to 30).
   
2. Install dependencies: pip install requests python-dotenv

3. Schedule with cron (daily at 8 AM):
   0 8 * * * /usr/bin/python3 /path/to/this/script.py
"""

import os
import sys
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Try to import dotenv for environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed. Using system environment variables.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ynab_email.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

class YNABEmailer:
    def __init__(self):
        # YNAB API Configuration
        self.ynab_token = os.getenv('YNAB_API_TOKEN')
        self.budget_id = os.getenv('BUDGET_ID')
        self.base_url = 'https://api.youneedabudget.com/v1'
        
        # Email Configuration
        self.email_host = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
        self.email_port = int(os.getenv('EMAIL_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_pass = os.getenv('EMAIL_PASS')
        self.to_email = os.getenv('TO_EMAIL')
        
        # Report configuration
        self.report_path = os.getenv('REPORT_PATH', os.path.dirname(os.path.abspath(__file__)))
        self.retain_report_days = int(os.getenv('RETAIN_REPORT_DAYS', '30'))
        
        # Validate required environment variables
        required_vars = [
            'YNAB_API_TOKEN', 'BUDGET_ID', 'EMAIL_USER', 
            'EMAIL_PASS', 'TO_EMAIL', 'INCLUDED_GROUPS'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Request headers for YNAB API
        self.headers = {
            'Authorization': f'Bearer {self.ynab_token}',
            'Content-Type': 'application/json'
        }

    def get_budget_summary(self) -> Dict:
        """Get budget name, current month, ready to assign amount, and credit card debt."""
        try:
            # Get budget info
            budget_response = requests.get(
                f'{self.base_url}/budgets/{self.budget_id}',
                headers=self.headers,
                timeout=30
            )
            budget_response.raise_for_status()
            budget_name = budget_response.json()['data']['budget']['name']
            
            # Get current month's ready to assign
            month_response = requests.get(
                f'{self.base_url}/budgets/{self.budget_id}/months/current',
                headers=self.headers,
                timeout=30
            )
            month_response.raise_for_status()
            month_data = month_response.json()['data']['month']
            
            # Convert milliunits to dollars
            ready_to_assign = month_data['to_be_budgeted'] / 1000
            
            # Format the month (YNAB returns YYYY-MM-DD format)
            month_date = datetime.strptime(month_data['month'], '%Y-%m-%d')
            month_name = month_date.strftime('%B %Y')  # e.g., "September 2025"
            
            # Get credit card debt total
            accounts_response = requests.get(
                f'{self.base_url}/budgets/{self.budget_id}/accounts',
                headers=self.headers,
                timeout=30
            )
            accounts_response.raise_for_status()
            accounts_data = accounts_response.json()['data']['accounts']
            
            credit_debt_total = 0
            for account in accounts_data:
                if account['type'] == 'creditCard' and not account['closed'] and not account['deleted']:
                    # Credit card balances are negative when you owe money
                    balance = account['balance'] / 1000
                    if balance < 0:
                        credit_debt_total += abs(balance)
            
            return {
                'budget_name': budget_name,
                'month_name': month_name,
                'ready_to_assign': ready_to_assign,
                'credit_debt_total': credit_debt_total
            }
            
        except Exception as e:
            logging.warning(f"Could not fetch budget summary: {e}")
            return {
                'budget_name': "Your Budget",
                'month_name': datetime.now().strftime('%B %Y'),
                'ready_to_assign': 0.0,
                'credit_debt_total': 0.0
            }

    def get_server_knowledge(self) -> Optional[int]:
        """Get the last known server_knowledge from a file."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        knowledge_file = os.path.join(script_dir, '.ynab_server_knowledge')
        
        try:
            if os.path.exists(knowledge_file):
                with open(knowledge_file, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            logging.warning(f"Could not read server knowledge: {e}")
        
        return None

    def save_server_knowledge(self, server_knowledge: int):
        """Save the server_knowledge to a file for next delta request."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        knowledge_file = os.path.join(script_dir, '.ynab_server_knowledge')
        
        try:
            with open(knowledge_file, 'w') as f:
                f.write(str(server_knowledge))
            logging.info(f"Saved server knowledge: {server_knowledge}")
        except Exception as e:
            logging.error(f"Could not save server knowledge: {e}")

    def get_recent_transactions(self, included_category_names: set) -> List[Dict]:
        """Get transactions using YNAB's delta request feature, filtered by included categories."""
        try:
            # Get last known server_knowledge
            last_server_knowledge = self.get_server_knowledge()
            
            # Build API URL with delta request if we have server knowledge
            url = f'{self.base_url}/budgets/{self.budget_id}/transactions'
            if last_server_knowledge:
                url += f'?last_knowledge_of_server={last_server_knowledge}'
                logging.info(f"Using delta request with server knowledge: {last_server_knowledge}")
            else:
                # First run - get transactions from the last 24 hours for initial data
                yesterday = datetime.now() - timedelta(days=1)
                since_date = yesterday.strftime('%Y-%m-%dT%H:%M:%SZ')
                url += f'?since_date={since_date}'
                logging.info("First run - fetching transactions from last 24 hours")
            
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            response_data = response.json()['data']
            transactions_data = response_data['transactions']
            current_server_knowledge = response_data['server_knowledge']
            
            # Save the new server_knowledge for next time
            self.save_server_knowledge(current_server_knowledge)
            
            # Filter for approved transactions only and matching categories
            recent_transactions = []
            for transaction in transactions_data:
                if (transaction['approved'] and 
                    not transaction['deleted']):
                    
                    category_name = transaction['category_name']
                    
                    # Only include transactions from categories in our report
                    if category_name and category_name in included_category_names:
                        # Convert amount from milliunits to dollars
                        amount = transaction['amount'] / 1000
                        
                        # Format date
                        date_obj = datetime.strptime(transaction['date'], '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%m/%d/%Y')
                        
                        recent_transactions.append({
                            'date': formatted_date,
                            'payee': transaction['payee_name'] or 'Unknown',
                            'memo': transaction['memo'] or '',
                            'category': category_name,
                            'amount': amount
                        })
            
            logging.info(f"Found {len(recent_transactions)} recent approved transactions in tracked categories")
            return sorted(recent_transactions, key=lambda x: x['date'], reverse=True)
            
        except Exception as e:
            logging.warning(f"Could not fetch recent transactions: {e}")
            return []
    def get_categories(self) -> List[Dict]:
        """Fetch categories with their balances from YNAB API, filtered by specific groups."""
        # Get the category groups to include from environment variable
        included_groups_env = os.getenv('INCLUDED_GROUPS')
        if not included_groups_env:
            raise ValueError("INCLUDED_GROUPS environment variable is required")
        included_groups = set(group.strip() for group in included_groups_env.split(','))
        
        try:
            response = requests.get(
                f'{self.base_url}/budgets/{self.budget_id}/categories',
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            categories_data = response.json()['data']['category_groups']
            categories = []
            
            for group in categories_data:
                group_name = group['name']
                
                # Skip hidden categories, credit card payments, and groups not in our list
                if (group['hidden'] or 
                    group_name == 'Credit Card Payments' or 
                    group_name not in included_groups):
                    continue
                
                for category in group['categories']:
                    if not category['hidden'] and not category['deleted']:
                        # Convert milliunits to dollars (YNAB stores amounts in milliunits)
                        balance = category['balance'] / 1000
                        budgeted = category['budgeted'] / 1000
                        activity = category['activity'] / 1000
                        
                        categories.append({
                            'group': group_name,
                            'name': category['name'],
                            'balance': balance,
                            'budgeted': budgeted,
                            'activity': activity
                        })
            
            logging.info(f"Filtered categories to include only: {', '.join(included_groups)}")
            return categories
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching categories from YNAB: {e}")
            raise
        except KeyError as e:
            logging.error(f"Unexpected API response format: {e}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise

    def format_currency(self, amount: float) -> str:
        """Format amount as currency."""
        if amount < 0:
            return f"-${abs(amount):,.2f}"
        return f"${amount:,.2f}"

    def create_html_table(self, categories: List[Dict], budget_summary: Dict, recent_transactions: List[Dict]) -> str:
        """Create an HTML table from categories data."""
        budget_name = budget_summary['budget_name']
        month_name = budget_summary['month_name']
        ready_to_assign = budget_summary['ready_to_assign']
        credit_debt_total = budget_summary['credit_debt_total']
        
        # Calculate total negative balances
        total_negative_balances = sum(abs(cat['balance']) for cat in categories if cat['balance'] < 0)
        
        # Determine colors
        debt_class = 'negative' if credit_debt_total > 0 else 'positive'
        negative_class = 'negative' if total_negative_balances > 0 else 'positive'
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                           color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header .month-info {{ font-size: 18px; margin-top: 15px; }}
                .header .metric {{ font-size: 18px; font-weight: bold; margin-top: 10px; }}
                .header .warning {{ font-size: 14px; margin-top: 5px; font-style: italic; }}
                h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .positive {{ color: #27ae60; font-weight: bold; }}
                .negative {{ color: #e74c3c; font-weight: bold; }}
                .zero {{ color: #95a5a6; }}
                .summary {{ margin-top: 30px; padding: 15px; background-color: #ecf0f1; border-radius: 5px; }}
                .transactions {{ margin-top: 30px; margin-bottom: 30px; }}
                .transactions table {{ margin-top: 10px; }}
                .transactions th {{ background-color: #e67e22; }}
                .amount-positive {{ color: #27ae60; font-weight: bold; }}
                .amount-negative {{ color: #e74c3c; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Rad's Budget Update</h1>
                <div class="month-info">{month_name}</div>
                <div class="metric">
                    Credit Card Debt Total: <span class="{debt_class}">{self.format_currency(credit_debt_total)}</span>
                </div>
                <div class="metric">
                    Negative Category Balances: <span class="{negative_class}">{self.format_currency(total_negative_balances)}</span>
                </div>
        """
        
        if total_negative_balances > 0:
            html += f"""
                <div class="warning">
                    ⚠️ This amount must be taken from other categories or credit card debt will be incurred
                </div>
            """
        
        html += """
            </div>
        """
        
        # Add recent transactions section FIRST
        if recent_transactions:
            html += f"""
            <div class="transactions">
                <h2>Recent Transactions</h2>
                <p>Approved transactions in tracked categories since last report ({len(recent_transactions)} transactions)</p>
                
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Payee</th>
                            <th>Category</th>
                            <th>Memo</th>
                            <th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for transaction in recent_transactions:
                amount_class = 'amount-positive' if transaction['amount'] >= 0 else 'amount-negative'
                html += f"""
                        <tr>
                            <td>{transaction['date']}</td>
                            <td>{transaction['payee']}</td>
                            <td>{transaction['category']}</td>
                            <td>{transaction['memo']}</td>
                            <td class="{amount_class}">{self.format_currency(transaction['amount'])}</td>
                        </tr>
                """
            
            html += """
                    </tbody>
                </table>
            </div>
            """
        else:
            html += """
            <div class="transactions">
                <h2>Recent Transactions</h2>
                <p>No new approved transactions in tracked categories since last report.</p>
            </div>
            """
        
        # NOW add the category balances section
        html += f"""
            <h2>Category Balances - {budget_name}</h2>
            <p>Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            
            <table>
                <thead>
                    <tr>
                        <th>Category Group</th>
                        <th>Category</th>
                        <th>Available Balance</th>
                        <th>Budgeted</th>
                        <th>Activity</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Group categories by category group
        current_group = None
        total_available = 0
        positive_balances = 0
        negative_balances = 0
        
        for category in sorted(categories, key=lambda x: (x['group'], x['name'])):
            balance = category['balance']
            total_available += balance
            
            if balance > 0:
                positive_balances += 1
                balance_class = 'positive'
            elif balance < 0:
                negative_balances += 1
                balance_class = 'negative'
            else:
                balance_class = 'zero'
            
            # Add group header if this is a new group
            group_cell = category['group'] if category['group'] != current_group else ''
            current_group = category['group']
            
            html += f"""
                    <tr>
                        <td><strong>{group_cell}</strong></td>
                        <td>{category['name']}</td>
                        <td class="{balance_class}">{self.format_currency(balance)}</td>
                        <td>{self.format_currency(category['budgeted'])}</td>
                        <td>{self.format_currency(category['activity'])}</td>
                    </tr>
            """
        
        # Summary section with Ready to Assign moved here
        rta_class = 'positive' if ready_to_assign >= 0 else 'negative'
        
        html += f"""
                </tbody>
            </table>
            
            <div class="summary">
                <h3>Summary</h3>
                <p><strong>Ready to Assign:</strong> 
                   <span class="{rta_class}">{self.format_currency(ready_to_assign)}</span>
                </p>
                <p><strong>Total Available Balance:</strong> 
                   <span class="{'positive' if total_available >= 0 else 'negative'}">
                   {self.format_currency(total_available)}
                   </span>
                </p>
                <p><strong>Categories with Positive Balances:</strong> {positive_balances}</p>
                <p><strong>Categories with Negative Balances:</strong> {negative_balances}</p>
                <p><strong>Total Categories:</strong> {len(categories)}</p>
            </div>
        </body>
        </html>
        """
        
        return html

    def save_html_report(self, html_content: str, budget_summary: Dict) -> str:
        """Save the HTML report to a timestamped file in the specified report path."""
        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ynab_report_{timestamp}.html"
            
            # Use the configured report path
            filepath = os.path.join(self.report_path, filename)
            
            # Write HTML content to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logging.info(f"HTML report saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logging.error(f"Error saving HTML report: {e}")
            raise

    def cleanup_old_reports(self):
        """Delete report files older than the specified retention period."""
        try:
            if not os.path.exists(self.report_path):
                logging.warning(f"Report path does not exist: {self.report_path}")
                return
            
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=self.retain_report_days)
            deleted_count = 0
            
            # Get all files in the report directory
            for filename in os.listdir(self.report_path):
                if filename.startswith('ynab_report_') and filename.endswith('.html'):
                    filepath = os.path.join(self.report_path, filename)
                    
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    
                    # Delete if older than cutoff
                    if file_mtime < cutoff_date:
                        try:
                            os.remove(filepath)
                            deleted_count += 1
                            logging.info(f"Deleted old report: {filename}")
                        except Exception as e:
                            logging.error(f"Error deleting file {filename}: {e}")
            
            if deleted_count > 0:
                logging.info(f"Cleaned up {deleted_count} old report files (older than {self.retain_report_days} days)")
            else:
                logging.info("No old report files to clean up")
                
        except Exception as e:
            logging.error(f"Error during report cleanup: {e}")

    def test_smtp_connection(self):
        """Test SMTP connection with detailed logging."""
        logging.info(f"Testing SMTP connection to {self.email_host}:{self.email_port}")
        
        try:
            # Test basic connection
            server = smtplib.SMTP(self.email_host, self.email_port)
            server.set_debuglevel(1)  # Enable debug output
            
            logging.info("SMTP connection established")
            
            # Test STARTTLS
            server.starttls()
            logging.info("STARTTLS successful")
            
            # Test authentication
            server.login(self.email_user, self.email_pass)
            logging.info("SMTP authentication successful")
            
            server.quit()
            logging.info("SMTP test completed successfully")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logging.error(f"SMTP Authentication failed: {e}")
            return False
        except smtplib.SMTPConnectError as e:
            logging.error(f"SMTP Connection failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logging.error(f"SMTP Error: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error during SMTP test: {e}")
            return False

    def send_email(self, html_content: str, budget_summary: Dict):
        """Send the formatted table via email."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = '"Rad\'s Budget Update" <YNAB@therads.com>'
            msg['To'] = self.to_email
            msg['Subject'] = f"Rad's Budget Update - {budget_summary['month_name']} - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email with more robust error handling
            logging.info(f"Attempting to send email via {self.email_host}:{self.email_port}")
            
            server = None
            try:
                # Create SMTP connection with longer timeout
                server = smtplib.SMTP(self.email_host, self.email_port, timeout=60)
                server.set_debuglevel(1)  # Enable debug for troubleshooting
                
                # Use STARTTLS
                server.starttls()
                
                # Login
                server.login(self.email_user, self.email_pass)
                
                # Send message
                server.send_message(msg)
                
                logging.info(f"Email sent successfully to {self.to_email}")
                
            except smtplib.SMTPAuthenticationError as e:
                logging.error(f"SMTP Authentication Error: {e}")
                logging.error("Check your email credentials and ensure app passwords are used if required")
                raise
            except smtplib.SMTPConnectError as e:
                logging.error(f"SMTP Connection Error: {e}")
                logging.error("Check your SMTP host and port settings")
                raise
            except smtplib.SMTPRecipientsRefused as e:
                logging.error(f"Recipients refused: {e}")
                raise
            except smtplib.SMTPServerDisconnected as e:
                logging.error(f"SMTP Server disconnected: {e}")
                logging.error("Try different port (465 for SSL) or check Migadu settings")
                raise
            except Exception as e:
                logging.error(f"Unexpected email error: {e}")
                raise
            finally:
                if server:
                    try:
                        server.quit()
                    except:
                        pass
                        
        except Exception as e:
            logging.error(f"Error in send_email method: {e}")
            raise

    def run(self):
        """Main execution method."""
        try:
            logging.info("Starting YNAB daily email report...")
            
            # Get budget summary (name, month, ready to assign)
            budget_summary = self.get_budget_summary()
            
            # Fetch categories
            logging.info("Fetching categories from YNAB...")
            categories = self.get_categories()
            
            if not categories:
                logging.warning("No categories found!")
                return
            
            logging.info(f"Found {len(categories)} categories")
            
            # Create set of category names for filtering transactions
            category_names = {cat['name'] for cat in categories}
            
            # Get recent transactions filtered by categories in the report
            recent_transactions = self.get_recent_transactions(category_names)
            
            # Create HTML table
            html_content = self.create_html_table(categories, budget_summary, recent_transactions)
            
            # Save HTML report to file
            report_path = self.save_html_report(html_content, budget_summary)
            
            # Clean up old reports
            self.cleanup_old_reports()
            
            # Send email
            self.send_email(html_content, budget_summary)
            
            logging.info(f"YNAB daily email report completed successfully! Report saved to: {report_path}")
            
        except Exception as e:
            logging.error(f"Error in main execution: {e}")
            # Optionally send error notification email
            try:
                error_msg = MIMEText(f"YNAB daily report failed with error: {str(e)}")
                error_msg['From'] = '"Rad\'s Budget Update" <YNAB@therads.com>'
                error_msg['To'] = self.to_email
                error_msg['Subject'] = f"YNAB Daily Report Error - {datetime.now().strftime('%Y-%m-%d')}"
                
                with smtplib.SMTP(self.email_host, self.email_port) as server:
                    server.starttls()
                    server.login(self.email_user, self.email_pass)
                    server.send_message(error_msg)
            except:
                pass  # Don't let email errors mask the original error
            
            sys.exit(1)


def main():
    """Entry point for the script."""
    try:
        emailer = YNABEmailer()
        
        # Add SMTP test option
        if len(sys.argv) > 1 and sys.argv[1] == '--test-smtp':
            logging.info("Running SMTP connection test...")
            if emailer.test_smtp_connection():
                print("✓ SMTP test successful!")
            else:
                print("✗ SMTP test failed - check logs for details")
            return
        
        emailer.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()