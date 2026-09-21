<?php

namespace App\Services;

use App\Models\ActivationRequest;
use RuntimeException;

class LicenseSigner
{
    public function create(ActivationRequest $request): string
    {
        if (! function_exists('sodium_crypto_sign_seed_keypair')) {
            throw new RuntimeException('PHP Sodium extension is required.');
        }

        $seed = base64_decode((string) config('telegram.license_private_key_seed'), true);
        if ($seed === false || strlen($seed) !== SODIUM_CRYPTO_SIGN_SEEDBYTES) {
            throw new RuntimeException('LICENSE_PRIVATE_KEY_SEED must be a Base64 encoded 32-byte Ed25519 seed.');
        }

        $payload = [
            'issued_at' => now('UTC')->format('Y-m-d\\TH:i:sP'),
            'license_id' => $request->id,
            'machine_id' => strtolower($request->machine_id),
            'plan' => 'lifetime',
        ];
        ksort($payload);
        $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        $keypair = sodium_crypto_sign_seed_keypair($seed);
        $signature = sodium_crypto_sign_detached($json, sodium_crypto_sign_secretkey($keypair));

        return $this->base64Url($json).'.'.$this->base64Url($signature);
    }

    private function base64Url(string $value): string
    {
        return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
    }
}
