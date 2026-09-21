<?php

namespace App\Http\Controllers;

use App\Models\ActivationRequest;
use App\Services\LicenseSigner;
use App\Services\TelegramService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Symfony\Component\HttpFoundation\Response;

class TelegramWebhookController extends Controller
{
    public function user(Request $request, TelegramService $telegram): JsonResponse
    {
        $this->validateSecret($request, (string) config('telegram.user_webhook_secret'));
        $message = $request->input('message');
        if (! is_array($message)) {
            return response()->json(['ok' => true]);
        }

        $chatId = (string) data_get($message, 'chat.id', '');
        $text = trim((string) data_get($message, 'text', ''));
        if ($chatId === '') {
            return response()->json(['ok' => true]);
        }

        if ($text === '/start') {
            $telegram->sendUserMessage($chatId, "សូមផ្ញើ Machine ID ចំនួន 32 តួអក្សរ ដើម្បីស្នើសុំ Activation Code។");
            return response()->json(['ok' => true]);
        }

        preg_match('/\\b[a-fA-F0-9]{32}\\b/', $text, $matches);
        if (! isset($matches[0])) {
            $telegram->sendUserMessage($chatId, "Machine ID មិនត្រឹមត្រូវ។ សូម Copy Machine ID ពី DeepXII Tools ហើយផ្ញើមកម្ដងទៀត។");
            return response()->json(['ok' => true]);
        }

        $machineId = strtolower($matches[0]);
        $existing = ActivationRequest::query()
            ->where('telegram_user_id', $chatId)
            ->where('machine_id', $machineId)
            ->latest()->first();

        if ($existing?->status === 'approved' && $existing->activation_code) {
            $telegram->sendUserMessage($chatId, "✅ Activation Code របស់អ្នក៖\n\n{$existing->activation_code}");
            return response()->json(['ok' => true]);
        }
        if ($existing?->status === 'pending') {
            $telegram->sendUserMessage($chatId, '⏳ សំណើរបស់អ្នកកំពុងរង់ចាំ Admin Approve។');
            return response()->json(['ok' => true]);
        }

        $activation = ActivationRequest::create([
            'telegram_user_id' => $chatId,
            'telegram_username' => data_get($message, 'from.username') ?: data_get($message, 'from.first_name'),
            'machine_id' => $machineId,
            'status' => 'pending',
        ]);
        $username = $activation->telegram_username ?: 'User';
        $telegram->sendAdminMessage(
            "Activation request\nUser: @{$username}\nMachine ID: {$machineId}\nRequest: {$activation->id}",
            ['inline_keyboard' => [[
                ['text' => '✅ Approve', 'callback_data' => "approve:{$activation->id}"],
                ['text' => '❌ Reject', 'callback_data' => "reject:{$activation->id}"],
            ]]],
        );
        $telegram->sendUserMessage($chatId, '✅ សំណើបានផ្ញើទៅ Admin។ សូមរង់ចាំការអនុម័ត។');

        return response()->json(['ok' => true]);
    }

    public function admin(Request $request, TelegramService $telegram, LicenseSigner $signer): JsonResponse
    {
        $this->validateSecret($request, (string) config('telegram.admin_webhook_secret'));
        $query = $request->input('callback_query');
        if (! is_array($query)) {
            return response()->json(['ok' => true]);
        }

        $callbackId = (string) data_get($query, 'id', '');
        if ((string) data_get($query, 'from.id') !== (string) config('telegram.admin_id')) {
            $telegram->answerAdminCallback($callbackId, 'Admin only', true);
            return response()->json(['ok' => true]);
        }

        [$action, $id] = array_pad(explode(':', (string) data_get($query, 'data'), 2), 2, null);
        if (! in_array($action, ['approve', 'reject'], true) || ! Str::isUuid($id)) {
            $telegram->answerAdminCallback($callbackId, 'Invalid request', true);
            return response()->json(['ok' => true]);
        }

        $result = DB::transaction(function () use ($id, $action, $signer) {
            $activation = ActivationRequest::query()->lockForUpdate()->find($id);
            if (! $activation || $activation->status !== 'pending') {
                return null;
            }
            if ($action === 'approve') {
                $activation->activation_code = $signer->create($activation);
                $activation->status = 'approved';
                $activation->approved_at = now();
            } else {
                $activation->status = 'rejected';
                $activation->rejected_at = now();
            }
            $activation->save();
            return $activation;
        });

        if (! $result) {
            $telegram->answerAdminCallback($callbackId, 'Request already handled');
            return response()->json(['ok' => true]);
        }

        if ($result->status === 'approved') {
            $telegram->sendUserMessage($result->telegram_user_id, "✅ Admin បាន Approve។\n\nCopy Activation Code នេះដាក់ក្នុង DeepXII Tools៖\n\n{$result->activation_code}");
            $callbackText = 'Approved and code sent';
        } else {
            $telegram->sendUserMessage($result->telegram_user_id, '❌ Admin បានបដិសេធសំណើ Activation របស់អ្នក។');
            $callbackText = 'Rejected';
        }

        $telegram->answerAdminCallback($callbackId, $callbackText);
        $messageChatId = data_get($query, 'message.chat.id');
        $messageId = data_get($query, 'message.message_id');
        if ($messageChatId !== null && $messageId !== null) {
            $telegram->editAdminMessage($messageChatId, (int) $messageId, "{$callbackText}\nMachine ID: {$result->machine_id}");
        }

        return response()->json(['ok' => true]);
    }

    private function validateSecret(Request $request, string $expected): void
    {
        $provided = (string) $request->header('X-Telegram-Bot-Api-Secret-Token', '');
        abort_if($expected === '' || ! hash_equals($expected, $provided), Response::HTTP_UNAUTHORIZED);
    }
}
