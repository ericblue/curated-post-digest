# Scheduling and Email Delivery Guide

This document outlines options for automating the Reddit digest system and delivering reports via email.

## Table of Contents

1. [Scheduling Options](#scheduling-options)
2. [Email Delivery Options](#email-delivery-options)
3. [Recommended Implementation](#recommended-implementation)
4. [Configuration Examples](#configuration-examples)

---

## Scheduling Options

### Option 1: LaunchAgent (Recommended for Mac)

**Best for:** Native macOS integration, background execution

LaunchAgents are macOS's native way to run scheduled tasks. They integrate seamlessly with the system and can run even when you're not actively using your Mac.

#### Advantages
- ✅ Native macOS integration
- ✅ No external dependencies
- ✅ Can run in background without terminal
- ✅ Easy to view logs via `log show`
- ✅ Can be configured to run when Mac wakes from sleep
- ✅ Simple enable/disable commands

#### Disadvantages
- ⚠️ Only runs when Mac is on (unless configured for wake)
- ⚠️ Requires plist file management

#### How It Works

1. **Configuration**: Add schedule settings to `config.yaml`
2. **Setup Script**: Generate LaunchAgent plist from config
3. **Installation**: Install plist to `~/Library/LaunchAgents/`
4. **Management**: Use `launchctl` commands to enable/disable

#### Example Configuration

```yaml
schedule:
  enabled: true
  frequency: weekly  # daily, weekly, monthly
  day_of_week: monday  # for weekly schedules
  time: "09:00"  # 24-hour format
  timezone: "America/Los_Angeles"
```

#### Implementation Structure

```
scripts/
  setup_schedule.sh    # Generate & install LaunchAgent plist
  schedule_runner.sh   # Wrapper script that runs the digest
```

#### Commands

```bash
make schedule-install   # Generate and install LaunchAgent
make schedule-uninstall # Remove LaunchAgent
make schedule-status    # Check if schedule is active
```

---

### Option 2: Cron (Traditional Unix Scheduler)

**Best for:** Simple, universal scheduling, familiar to developers

Cron is the traditional Unix scheduler available on macOS and Linux.

#### Advantages
- ✅ Universal and well-documented
- ✅ Simple syntax
- ✅ No extra setup required
- ✅ Works on any Unix-like system

#### Disadvantages
- ⚠️ On macOS, cron may not run if Mac is asleep
- ⚠️ Less integrated with macOS system
- ⚠️ Requires manual `crontab -e` editing

#### How It Works

1. **Edit Crontab**: `crontab -e`
2. **Add Schedule**: Add cron expression
3. **Save**: Cron automatically picks up changes

#### Example Cron Entry

```bash
# Run weekly digest every Monday at 9:00 AM
0 9 * * 1 cd /path/to/project && make weekly
```

#### Cron Syntax

```
* * * * * command
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7, Sunday = 0 or 7)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

#### Common Examples

```bash
# Daily at 9:00 AM
0 9 * * * cd /path/to/project && make daily

# Weekly on Monday at 9:00 AM
0 9 * * 1 cd /path/to/project && make weekly

# Monthly on the 1st at 9:00 AM
0 9 1 * * cd /path/to/project && make monthly

# Every 6 hours
0 */6 * * * cd /path/to/project && make daily
```

---

### Option 3: Python-Based Scheduler

**Best for:** Complex scheduling logic, cross-platform, programmatic control

Use Python's `schedule` library or similar to create a long-running scheduler process.

#### Advantages
- ✅ Flexible scheduling rules
- ✅ Can add retry logic and error handling
- ✅ Easy to test and debug
- ✅ Cross-platform

#### Disadvantages
- ⚠️ Requires a long-running process
- ⚠️ More complex setup
- ⚠️ Needs process management (daemon/service)

#### How It Works

1. **Install Library**: `pip install schedule`
2. **Create Scheduler Script**: Python script with schedule definitions
3. **Run as Service**: Use `launchd` or `systemd` to keep it running

#### Example Implementation

```python
import schedule
import time
import subprocess

def run_digest():
    subprocess.run(["make", "weekly"], cwd="/path/to/project")

schedule.every().monday.at("09:00").do(run_digest)

while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## Email Delivery Options

### Option 1: macOS `mail` Command (Simplest)

**Best for:** Quick setup, local email delivery

Uses macOS's built-in `mail` command, which requires Mail.app to be configured.

#### Advantages
- ✅ No additional dependencies
- ✅ Simple one-line command
- ✅ Works immediately if Mail.app is set up

#### Disadvantages
- ⚠️ Requires Mail.app to be configured with an email account
- ⚠️ Limited formatting options
- ⚠️ May end up in spam folder

#### Usage

```bash
# Send report as email body
mail -s "Weekly AI Digest" user@example.com < output/latest/report.md

# Send with attachment
uuencode output/latest/report.md report.md | mail -s "Weekly AI Digest" user@example.com
```

#### Integration

Add to `run_digest.sh` or create separate `send_email.sh`:

```bash
#!/bin/bash
if [ -f "output/latest/report.md" ]; then
    mail -s "Weekly AI Digest - $(date +%Y-%m-%d)" \
         "$EMAIL_RECIPIENT" < output/latest/report.md
fi
```

---

### Option 2: Python `smtplib` (More Control)

**Best for:** Professional email delivery, HTML formatting, attachments

Use Python's built-in `smtplib` to send emails via SMTP (Gmail, custom SMTP, etc.).

#### Advantages
- ✅ Full control over email format
- ✅ Can send HTML emails
- ✅ Can attach files
- ✅ Works with any SMTP server
- ✅ More reliable delivery

#### Disadvantages
- ⚠️ Requires SMTP credentials
- ⚠️ More setup required
- ⚠️ Gmail requires app-specific passwords

#### Example Configuration

```yaml
email:
  enabled: true
  method: "smtp"
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  use_tls: true
  username: "your-email@gmail.com"
  password: "app-specific-password"  # Or use environment variable
  from: "your-email@gmail.com"
  to: "recipient@example.com"
  subject: "Weekly AI Digest"
```

#### Example Implementation

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(config, report_path):
    msg = MIMEMultipart()
    msg['From'] = config['from']
    msg['To'] = config['to']
    msg['Subject'] = config['subject']
    
    with open(report_path, 'r') as f:
        body = f.read()
    
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
        server.starttls()
        server.login(config['username'], config['password'])
        server.send_message(msg)
```

#### Gmail Setup

1. Enable 2-factor authentication
2. Generate app-specific password: https://myaccount.google.com/apppasswords
3. Use app-specific password in config (not your regular password)

---

### Option 3: External Service (Most Reliable)

**Best for:** Production use, high deliverability, no SMTP setup

Use services like SendGrid, Mailgun, or webhooks to Zapier/IFTTT.

#### Advantages
- ✅ High deliverability rates
- ✅ No SMTP configuration needed
- ✅ Free tiers available
- ✅ Analytics and tracking
- ✅ Webhook integration possible

#### Disadvantages
- ⚠️ Requires external service account
- ⚠️ API keys needed
- ⚠️ Potential costs at scale

#### SendGrid Example

```python
import sendgrid
from sendgrid.helpers.mail import Mail

def send_email_sendgrid(api_key, to_email, report_path):
    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    
    with open(report_path, 'r') as f:
        content = f.read()
    
    message = Mail(
        from_email='your-email@example.com',
        to_emails=to_email,
        subject='Weekly AI Digest',
        plain_text_content=content
    )
    
    response = sg.send(message)
    return response.status_code
```

#### Webhook to Zapier/IFTTT

1. Create Zapier/IFTTT webhook
2. Send report content via HTTP POST
3. Zapier/IFTTT handles email delivery

```bash
curl -X POST https://hooks.zapier.com/hooks/catch/xxx/ \
  -H "Content-Type: application/json" \
  -d '{"report": "'"$(cat output/latest/report.md | jq -Rs .)"'"}'
```

---

## Recommended Implementation

### Suggested Structure

Add to `config.yaml`:

```yaml
# Scheduling configuration
schedule:
  enabled: false  # Set to true to enable
  method: "launchagent"  # launchagent, cron, or python
  frequency: weekly  # daily, weekly, monthly
  day_of_week: monday  # for weekly schedules
  time: "09:00"  # 24-hour format
  timezone: "America/Los_Angeles"

# Email delivery configuration
email:
  enabled: false  # Set to true to enable
  method: "smtp"  # mail, smtp, or webhook
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  use_tls: true
  username: ""  # Or use EMAIL_USERNAME env var
  password: ""  # Or use EMAIL_PASSWORD env var (recommended)
  from: "your-email@gmail.com"
  to: "recipient@example.com"
  subject: "Weekly AI Digest - {date}"  # {date} will be replaced
```

### Implementation Files

```
scripts/
  setup_schedule.sh    # Generate & install LaunchAgent plist
  schedule_runner.sh   # Wrapper that runs digest + email
  send_email.py        # Email delivery script
```

### Workflow

1. **Schedule Setup**: Run `make schedule-install` to set up LaunchAgent
2. **Automatic Execution**: LaunchAgent runs `schedule_runner.sh` at scheduled time
3. **Digest Generation**: Script runs `make weekly` (or daily/monthly)
4. **Email Delivery**: If enabled, sends report via configured method
5. **Logging**: All output logged to `~/Library/Logs/reddit-digest/`

### Commands

```bash
# Setup scheduling
make schedule-install      # Install LaunchAgent
make schedule-uninstall    # Remove LaunchAgent
make schedule-status       # Check if schedule is active
make schedule-logs         # View recent logs

# Test email (without scheduling)
make test-email           # Send test email with latest report
```

---

## Configuration Examples

### Example 1: Weekly Digest with Gmail

```yaml
schedule:
  enabled: true
  method: "launchagent"
  frequency: weekly
  day_of_week: monday
  time: "09:00"
  timezone: "America/Los_Angeles"

email:
  enabled: true
  method: "smtp"
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  use_tls: true
  username: "your-email@gmail.com"
  # password: set via EMAIL_PASSWORD environment variable
  from: "your-email@gmail.com"
  to: "recipient@example.com"
  subject: "Weekly AI Digest - {date}"
```

### Example 2: Daily Digest with macOS Mail

```yaml
schedule:
  enabled: true
  method: "cron"
  frequency: daily
  time: "08:00"

email:
  enabled: true
  method: "mail"
  to: "user@example.com"
```

### Example 3: Monthly Digest with SendGrid

```yaml
schedule:
  enabled: true
  method: "launchagent"
  frequency: monthly
  day_of_month: 1
  time: "10:00"

email:
  enabled: true
  method: "webhook"
  webhook_url: "https://hooks.zapier.com/hooks/catch/xxx/"
  # Or use SendGrid API key
```

---

## Security Considerations

### Email Credentials

**Never commit credentials to git!**

1. **Environment Variables** (Recommended):
   ```bash
   export EMAIL_PASSWORD="your-app-specific-password"
   export EMAIL_USERNAME="your-email@gmail.com"
   ```

2. **Separate Config File** (Alternative):
   ```bash
   # Add to .gitignore
   config.secrets.yaml
   ```

3. **Keychain** (macOS):
   ```bash
   security add-generic-password -a "reddit-digest" -s "email" -w "password"
   ```

### LaunchAgent Permissions

LaunchAgents run with your user permissions. Ensure:
- Scripts are executable: `chmod +x scripts/*.sh`
- Paths are absolute or use `$HOME`
- Logs directory exists and is writable

---

## Troubleshooting

### LaunchAgent Not Running

```bash
# Check if loaded
launchctl list | grep reddit-digest

# View logs
log show --predicate 'process == "reddit-digest"' --last 1h

# Manually test
launchctl start ~/Library/LaunchAgents/com.reddit-digest.plist
```

### Email Not Sending

1. **Test SMTP connection**:
   ```python
   import smtplib
   server = smtplib.SMTP('smtp.gmail.com', 587)
   server.starttls()
   server.login('username', 'password')
   ```

2. **Check credentials**: Verify username/password are correct
3. **Check spam folder**: Emails may be filtered
4. **Test with mail command**: `echo "test" | mail -s "test" your@email.com`

### Cron Not Running

1. **Check cron is running**: `ps aux | grep cron`
2. **Check cron logs**: `/var/log/system.log` (macOS)
3. **Verify paths**: Use absolute paths in cron entries
4. **Check permissions**: Ensure scripts are executable

---

## Next Steps

1. **Choose your scheduling method**: LaunchAgent (recommended for Mac) or Cron
2. **Choose your email method**: SMTP (most control) or mail command (simplest)
3. **Configure `config.yaml`**: Add schedule and email sections
4. **Test manually**: Run `make weekly` and test email sending
5. **Set up automation**: Install schedule and enable email delivery

For implementation details, see the main [README](../README.md) and [Technical Documentation](TECHNICAL.md).


