<?php

use App\Http\Controllers\TelegramWebhookController;
use Illuminate\Support\Facades\Route;

Route::post('/telegram/user/webhook', [TelegramWebhookController::class, 'user']);
Route::post('/telegram/admin/webhook', [TelegramWebhookController::class, 'admin']);
