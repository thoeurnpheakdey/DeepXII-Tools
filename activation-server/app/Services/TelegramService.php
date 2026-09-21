<?php

namespace App\Services;

use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Facades\Http;
use RuntimeException;

class TelegramService
{
    public function userBot(): PendingRequest
    {
        return $this->bot((string) config('telegram.user_bot_token'));
    }

    public function adminBot(): PendingRequest
    {
        return $this->bot((string) config('telegram.admin_bot_token'));
    }

    public function sendUserMessage(string $chatId, string $text, ?array $replyMarkup = null): void
    {
        $payload = ['chat_id' => $chatId, 'text' => $text];
        if ($replyMarkup !== null) {
            $payload['reply_markup'] = $replyMarkup;
        }
        $this->post($this->userBot(), 'sendMessage', $payload);
    }

    public function sendAdminMessage(string $text, array $replyMarkup): void
    {
        $this->post($this->adminBot(), 'sendMessage', [
            'chat_id' => (string) config('telegram.admin_id'),
            'text' => $text,
            'reply_markup' => $replyMarkup,
        ]);
    }

    public function answerAdminCallback(string $callbackId, string $text, bool $alert = false): void
    {
        $this->post($this->adminBot(), 'answerCallbackQuery', [
            'callback_query_id' => $callbackId,
            'text' => $text,
            'show_alert' => $alert,
        ]);
    }

    public function editAdminMessage(int|string $chatId, int $messageId, string $text): void
    {
        $this->post($this->adminBot(), 'editMessageText', [
            'chat_id' => $chatId,
            'message_id' => $messageId,
            'text' => $text,
        ]);
    }

    private function bot(string $token): PendingRequest
    {
        if ($token === '') {
            throw new RuntimeException('Telegram bot token is not configured.');
        }

        return Http::acceptJson()->asJson()->timeout(20)
            ->baseUrl("https://api.telegram.org/bot{$token}");
    }

    private function post(PendingRequest $bot, string $method, array $payload): void
    {
        $response = $bot->post($method, $payload);
        if (! $response->successful() || ! $response->json('ok')) {
            throw new RuntimeException("Telegram {$method} failed: ".$response->body());
        }
    }
}
