<?php

use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return response()->json([
        'service' => 'DeepXII Activation Server',
        'status' => 'online',
    ]);
});
