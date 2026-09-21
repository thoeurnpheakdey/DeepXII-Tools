<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

Artisan::command('activation:repair-partial-migration', function () {
    if (! Schema::hasTable('users')) {
        $this->info('No partial users table was found.');
        return;
    }
    if (DB::table('users')->count() !== 0) {
        $this->error('The users table contains data and was not changed.');
        return;
    }
    Schema::rename('users', '_failed_users_backup');
    $this->info('The empty partial users table was renamed as a backup.');
})->purpose('Safely recover from the legacy MySQL index migration failure');
