<?php

namespace Tests\Unit;

use App\Models\ActivationRequest;
use App\Services\LicenseSigner;
use Tests\TestCase;

class LicenseSignerTest extends TestCase
{
    public function test_it_creates_a_verifiable_machine_bound_code(): void
    {
        if (! extension_loaded('sodium')) {
            $this->markTestSkipped('PHP Sodium extension is not enabled on this machine.');
        }

        $keypair = sodium_crypto_sign_keypair();
        $secret = sodium_crypto_sign_secretkey($keypair);
        $seed = substr($secret, 0, SODIUM_CRYPTO_SIGN_SEEDBYTES);
        config()->set('telegram.license_private_key_seed', base64_encode($seed));

        $request = new ActivationRequest(['machine_id' => '0123456789abcdef0123456789abcdef']);
        $request->id = '550e8400-e29b-41d4-a716-446655440000';
        $code = app(LicenseSigner::class)->create($request);
        [$payload, $signature] = explode('.', $code, 2);
        $decode = fn (string $value) => base64_decode(strtr($value, '-_', '+/'));
        $payloadBytes = $decode($payload);

        $this->assertTrue(sodium_crypto_sign_verify_detached(
            $decode($signature),
            $payloadBytes,
            sodium_crypto_sign_publickey($keypair),
        ));
        $this->assertSame($request->machine_id, json_decode($payloadBytes, true)['machine_id']);
    }
}
