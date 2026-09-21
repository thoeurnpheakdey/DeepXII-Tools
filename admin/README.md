# DeepXII Activation Bot

The Telegram bot approves a Machine ID and returns an Ed25519-signed activation code. The private key stays on the Admin machine and is never bundled with DeepXII Tools.

## First-time setup

1. Create a bot with `@BotFather`.
2. Run `python admin/generate_license_keys.py` once. This has already been done for the current key pair.
3. Keep `admin/license_private_key.pem` private and back it up securely. Losing it means new codes cannot be issued for the bundled public key.
4. Create two bots: a **User Activation Bot** and an **Admin Approval Bot**.
5. Set both bot tokens and the numeric Telegram Admin ID in PowerShell:

```powershell
$env:DEEPXII_USER_BOT_TOKEN="USER_ACTIVATION_BOT_TOKEN"
$env:DEEPXII_ADMIN_BOT_TOKEN="ADMIN_APPROVAL_BOT_TOKEN"
$env:DEEPXII_ADMIN_ID="NUMERIC_ADMIN_TELEGRAM_ID"
python admin\activation_bot.py
```

The process must remain running. The User Bot receives Machine IDs and sends activation codes. The Admin Bot sends Approve/Reject buttons to the Admin account. Never commit either token or the private key.

Instead of PowerShell environment variables, copy `admin/bot.env.example` to `admin/bot.env`, replace the three placeholder values, and run `python admin\activation_bot.py`. The real `bot.env` is ignored by Git.

To find the numeric Admin ID without a third-party bot, send `/start` to your Admin Approval Bot and run `python admin\get_telegram_id.py`.

## App configuration

Set `activation_bot_username` to the bot username without `@` in the app configuration/default before producing the public installer. Users can then click **Open Telegram Activation Bot**, send their Machine ID, wait for approval, and paste the returned code into the activation screen.
