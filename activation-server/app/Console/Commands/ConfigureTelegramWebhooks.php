<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

class ConfigureTelegramWebhooks extends Command
{
    protected $signature = 'telegram:webhooks {--remove : Remove both webhooks}';
    protected $description = 'Configure the DeepXII Telegram bot webhooks';

    public function handle(): int
    {
        $remove = (bool) $this->option('remove');
        $baseUrl = rtrim((string) config('app.url'), '/');
        $bots = [
            'User' => [config('telegram.user_bot_token'), '/api/telegram/user/webhook', config('telegram.user_webhook_secret'), ['message']],
            'Admin' => [config('telegram.admin_bot_token'), '/api/telegram/admin/webhook', config('telegram.admin_webhook_secret'), ['callback_query']],
        ];

        foreach ($bots as $name => [$token, $path, $secret, $updates]) {
            if (! $token || (! $remove && ! $secret)) {
                $this->error("{$name} bot token or webhook secret is missing.");
                return self::FAILURE;
            }
            $method = $remove ? 'deleteWebhook' : 'setWebhook';
            $payload = $remove ? ['drop_pending_updates' => false] : [
                'url' => $baseUrl.$path,
                'secret_token' => $secret,
                'allowed_updates' => $updates,
                'drop_pending_updates' => false,
            ];
            $response = Http::asJson()->timeout(20)->post("https://api.telegram.org/bot{$token}/{$method}", $payload);
            if (! $response->successful() || ! $response->json('ok')) {
                $this->error("{$name} webhook failed: ".$response->body());
                return self::FAILURE;
            }
            $this->info("{$name} webhook ".($remove ? 'removed.' : "set to {$baseUrl}{$path}."));
        }

        return self::SUCCESS;
    }
}
