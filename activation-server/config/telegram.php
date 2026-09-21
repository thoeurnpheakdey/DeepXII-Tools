<?php

return [
    'user_bot_token' => env('TELEGRAM_USER_BOT_TOKEN'),
    'admin_bot_token' => env('TELEGRAM_ADMIN_BOT_TOKEN'),
    'admin_id' => (string) env('TELEGRAM_ADMIN_ID', ''),
    'user_webhook_secret' => env('TELEGRAM_USER_WEBHOOK_SECRET'),
    'admin_webhook_secret' => env('TELEGRAM_ADMIN_WEBHOOK_SECRET'),
    'license_private_key_seed' => env('LICENSE_PRIVATE_KEY_SEED'),
];
