<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('activation_requests', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->string('telegram_user_id');
            $table->string('telegram_username')->nullable();
            $table->char('machine_id', 32)->index();
            $table->string('status', 20)->default('pending')->index();
            $table->text('activation_code')->nullable();
            $table->timestamp('approved_at')->nullable();
            $table->timestamp('rejected_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('activation_requests');
    }
};
