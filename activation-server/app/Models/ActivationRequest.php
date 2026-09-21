<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;

class ActivationRequest extends Model
{
    use HasUuids;

    protected $fillable = [
        'telegram_user_id',
        'telegram_username',
        'machine_id',
        'status',
        'activation_code',
        'approved_at',
        'rejected_at',
    ];

    protected function casts(): array
    {
        return [
            'approved_at' => 'datetime',
            'rejected_at' => 'datetime',
        ];
    }
}
