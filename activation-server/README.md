# DeepXII Activation Server

Laravel 12 webhook server for the two DeepXII Telegram bots.

## Hosting requirements

- PHP 8.2 or newer with Sodium, cURL, PDO MySQL and Mbstring
- MySQL/MariaDB and Composer
- HTTPS enabled for `https://activate.goatplay.site`
- Domain document root pointing to this project's `public` directory

## Deploy

1. Upload this project to the server (do not upload the local `.env`).
2. Run `composer install --no-dev --optimize-autoloader`.
3. Copy `.env.example` to `.env` and fill in MySQL credentials, both bot tokens, Admin ID, webhook secrets and license seed.
4. Run `php artisan key:generate` and `php artisan migrate --force`.
5. Run `php artisan config:cache` and `php artisan route:cache`.
6. Run `php artisan telegram:webhooks` once. No long-running terminal is needed afterward.

Webhook URLs:

- `https://activate.goatplay.site/api/telegram/user/webhook`
- `https://activate.goatplay.site/api/telegram/admin/webhook`

## License key compatibility

On the development computer, run `python admin/export_laravel_license_seed.py` from the parent DeepXII project. Copy its single output line into the server `.env`. Never publish or commit that value.

## Security

The `.env` file and Ed25519 private seed are secrets. Keep a secure backup of the original `admin/license_private_key.pem`; losing it prevents generating codes compatible with existing desktop builds. Because the bot tokens were previously shared in chat, regenerate both through BotFather before production deployment and put only the new values in the server `.env`.
